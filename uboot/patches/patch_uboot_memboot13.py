#!/usr/bin/env python3
"""Build #39 (memboot13): measure the measurement channel, not the kernel.

Every reading this session came through tb_ram_rd64() reading what a previous
boot left in DRAM, and the last few came back with bits missing:

    0x5a11c0de -> 0x0a1140da   (stub magic)
    0xab800000 -> 0xa3000000   (the FDT pointer we passed)
    0x5a5a5a5a -> 0x52485a50   (the old canary)

so the channel is the suspect, not the kernel. This build measures the channel
with four independent readings, none of which needs the previous boot's word:

  1. U-Boot prints its own CurrentEL / SCTLR / TTBR0_EL1 / TCR_EL1 straight out
     of the registers. SCTLR bit 0 says whether the MMU is on, and this matters:
     dcache_disable() returns early when the data cache is already off, so it
     never reaches the store that clears both C and M - the MMU can be left on
     by cleanup_before_linux(). There is no way to second-guess a register read.

  2. Oracle: FNV-1a-32 over the first megabyte of the gunzipped kernel, compared
     against the value computed offline from the file that was flashed
     (0xa6c6918a). A hash of a megabyte of RAM can only match if the load path
     is byte-exact, which settles "is the channel trustworthy" on its own,
     without any record having to survive anything.

  3. U-Boot's own canaries at three addresses: the old scratch at 0x8f000000,
     a second at 0x89000000 in the same bank but never written before, and a
     third at 0xaaa00000 - just past the end of the kernel image, i.e. in the
     region the v9 control run already proved comes back intact through a reset
     (it filled the .bss window with 5a5a and read a screen of 'Z' next boot).
     Each is read back in the same run (the store and load paths agree) and
     again at the top of the next boot (the region survives XBL and the reset).

  4. The stub and its record move from 0x8f000000 to 0xaaa00400, in that proven
     region, so the x0 / EL / SCTLR it captures are not read back through an
     address that was never itself verified.

Readings that have been zero for many builds are dropped to make room: the
boot_args ladder (its three variables are all written before the kernel can
die), the bank listing, and the DTB bookkeeping. The printk ring dump is now
gated on a write pointer that says printk actually ran - with head_lpos at its
initial value it was printing garbage over the diagnostics above it, which is
what the scattered characters in the 23:31 photo were.
"""
import io
import re

P = "/home/meteor/u-boot-13r/common/board_r.c"
I = "/home/meteor/u-boot-13r/lib/initcall.c"

T = "\t"

s = io.open(P, encoding="utf-8", errors="surrogateescape").read()
ic = io.open(I, encoding="utf-8", errors="surrogateescape").read()


def sub1(text, pat, rep, name):
    new, n = re.subn(pat, lambda m: rep, text, count=1)
    assert n == 1, ("EDIT FAILED: " + name, n)
    return new


def sub1_group(text, pat, make, name):
    """Replace with a value built from the match (for keeping the match)."""
    new, n = re.subn(pat, make, text, count=1)
    assert n == 1, ("EDIT FAILED: " + name, n)
    return new


# ---------------------------------------------------------------------------
# lib/initcall.c: tb_logv2(), one line carrying two values.
# ---------------------------------------------------------------------------
NEWLOGV2 = (
    "\n"
    "/* Same as tb_logv(), but with two values on the line: the screen holds\n"
    " * about 28 lines at this pitch and the hand-off needs twelve readings. */\n"
    "void tb_logv2(const char *label, ulong a, ulong b)\n"
    "{\n"
    + T + "char buf[80];\n"
    + T + "const char *hex = \"0123456789abcdef\";\n"
    + T + "int i = 0, j;\n"
    "\n"
    + T + "while (label[i] && i < 32) {\n"
    + T + T + "buf[i] = label[i];\n"
    + T + T + "i++;\n"
    + T + "}\n"
    + T + "buf[i++] = ' ';\n"
    + T + "for (j = 0; j < 8; j++)\n"
    + T + T + "buf[i++] = hex[(a >> (28 - 4 * j)) & 0xf];\n"
    + T + "buf[i++] = ' ';\n"
    + T + "for (j = 0; j < 8; j++)\n"
    + T + T + "buf[i++] = hex[(b >> (28 - 4 * j)) & 0xf];\n"
    + T + "buf[i] = 0;\n"
    + T + "tb_screen_log(buf, 3);\n"
    "}\n"
)

TB_LOGV_PAT = r"void tb_logv\(const char \*label, ulong v\)\n\{\n[\s\S]*?\n\}\n"
ic = sub1_group(ic, TB_LOGV_PAT, lambda m: m.group(0) + NEWLOGV2, "tb_logv2")

io.open(I, "w", encoding="utf-8", errors="surrogateescape").write(ic)

# ---------------------------------------------------------------------------
# board_r.c
# ---------------------------------------------------------------------------

# 1) probe addresses: the stub and its record move to the region the control
#    run proved, and the three canary addresses are named.
OLD_DEFS = (
    "#define TB_STUB_ADDR" + T + T + "0x8f008000UL\n"
    "#define TB_STUB_SCRATCH" + T + T + "0x8f000000UL\n"
    "#define TB_STUB_MAGIC" + T + T + "0x5a11c0deUL\n"
)
NEW_DEFS = (
    "#define TB_STUB_ADDR" + T + T + "0xaaa08000UL\n"
    "#define TB_STUB_SCRATCH" + T + T + "0xaaa00400UL\n"
    "#define TB_STUB_MAGIC" + T + T + "0x5a11c0deUL\n"
    "\n"
    "/* U-Boot's own canaries. 0xaaa00000 sits just past the end of the kernel\n"
    " * image, in the region the v9 control run proved comes back intact through\n"
    " * a reset; 0x8f000000 is where the stub's record lived when it came back\n"
    " * with bits missing; 0x89000000 is in the same bank but never used. */\n"
    "#define TB_PRB_OFF" + T + T + "0x100UL\n"
    "#define TB_PRB1" + T + T + T + "0x8f000000UL\n"
    "#define TB_PRB2" + T + T + T + "0x89000000UL\n"
    "#define TB_PRB3" + T + T + T + "0xaaa00000UL\n"
    "\n"
    "/* FNV-1a-32 over the first megabyte of the gunzipped kernel, from the file\n"
    " * that was flashed: a read path that returns this from RAM is exact. */\n"
    "#define TB_ORACLE_LEN" + T + T + "0x100000UL\n"
    "#define TB_ORACLE_FNV" + T + T + "0xa6c6918aUL\n"
)
s = sub1(s, re.escape(OLD_DEFS), NEW_DEFS, "probe addresses")

# 2) the three readers and the byte-wise store that mirrors tb_ram_rd64()
HELPERS = (
    "/* The MMU is the one piece of state this project has been guessing at, so\n"
    " * read it instead: current_el() and get_sctlr() give this boot's level and\n"
    " * its SCTLR, and TTBR0/TCR say whether there is a translation table behind\n"
    " * it at all. */\n"
    "static ulong tb_mrs_ttbr0_el1(void)\n"
    "{\n"
    + T + "ulong v;\n"
    "\n"
    + T + "__asm__ volatile(\"mrs %0, ttbr0_el1\" : \"=r\" (v) : : \"cc\");\n"
    + T + "return v;\n"
    "}\n"
    "\n"
    "static ulong tb_mrs_tcr_el1(void)\n"
    "{\n"
    + T + "ulong v;\n"
    "\n"
    + T + "__asm__ volatile(\"mrs %0, tcr_el1\" : \"=r\" (v) : : \"cc\");\n"
    + T + "return v;\n"
    "}\n"
    "\n"
    "static u32 tb_fnv1a32(ulong addr, ulong len)\n"
    "{\n"
    + T + "u32 h = 2166136261U;\n"
    + T + "ulong i;\n"
    "\n"
    + T + "for (i = 0; i < len; i++) {\n"
    + T + T + "h ^= *(volatile unsigned char *)(addr + i);\n"
    + T + T + "h *= 16777619U;\n"
    + T + "}\n"
    + T + "return h;\n"
    "}\n"
    "\n"
    "/* Mirror of tb_ram_rd64(): a byte at a time, so the store and the load are\n"
    " * the same width and a mismatch cannot come from the access size. */\n"
    "static void tb_ram_wr64(ulong addr, u64 val)\n"
    "{\n"
    + T + "int i;\n"
    "\n"
    + T + "for (i = 0; i < 8; i++)\n"
    + T + T + "*(volatile unsigned char *)(addr + i) = (val >> (8 * i)) & 0xff;\n"
    "}\n"
    "\n"
)
s = sub1(s, re.escape("int cleanup_before_linux(void);\n"), HELPERS +
         "int cleanup_before_linux(void);\n", "helpers")

# 3) declare tb_logv2()
s = sub1(s, re.escape("void tb_logv(const char *label, ulong v);\n"),
         "void tb_logv(const char *label, ulong v);\n"
         "void tb_logv2(const char *label, ulong a, ulong b);\n", "tb_logv2 decl")

# 4) this boot's own level and MMU state, plus the three canaries from the
#    previous boot, before anything else the routine prints.
OLD = (T + T + "int nb = 0, i;\n"
       + T + T + "int rc;\n")
NEW = (OLD
       + "\n"
       + T + T + "tb_logv(\"UB EL\", (ulong)current_el());\n"
       + T + T + "tb_logv(\"UB SCTLR\", get_sctlr());\n"
       + T + T + "tb_logv(\"UB TTBR0\", tb_mrs_ttbr0_el1());\n"
       + T + T + "tb_logv(\"UB TCR\", tb_mrs_tcr_el1());\n"
       + "\n"
       + T + T + "/* What the previous boot wrote on its way out. Same-run and\n"
       + T + T + " * next-boot readings of the same three addresses separate a\n"
       + T + T + " * broken store path from a broken region. */\n"
       + T + T + "tb_logv(\"PV1\", tb_ram_rd64(TB_PRB1 + TB_PRB_OFF));\n"
       + T + T + "tb_logv(\"PV2\", tb_ram_rd64(TB_PRB2 + TB_PRB_OFF));\n"
       + T + T + "tb_logv(\"PV3\", tb_ram_rd64(TB_PRB3 + TB_PRB_OFF));\n"
       + T + T + "tb_logv2(\"STUB\", tb_ram_rd64(TB_STUB_SCRATCH + 32),\n"
       + T + T + T + " tb_ram_rd64(TB_STUB_SCRATCH));\n"
       + T + T + "tb_logv2(\"STUBE\", tb_ram_rd64(TB_STUB_SCRATCH + 8),\n"
       + T + T + T + " tb_ram_rd64(TB_STUB_SCRATCH + 16));\n")
s = sub1(s, re.escape(OLD), NEW, "own state + canaries")

# 5) drop the bank listing
OLD = (T + T + "tb_logv(\"RAM BANKS\", (ulong)nb);\n"
       + T + T + "tb_logv(\"RAM TOT\", (ulong)rtot);\n"
       + T + T + "for (i = 0; i < nb && i < 2; i++) {\n"
       + T + T + T + "tb_logv(i ? \"BANK1 START\" : \"BANK0 START\", (ulong)rb_start[i]);\n"
       + T + T + T + "tb_logv(i ? \"BANK1 SIZE\" : \"BANK0 SIZE\", (ulong)rb_size[i]);\n"
       + T + T + "}\n")
NEW = T + T + "tb_logv(\"RAM TOT\", (ulong)rtot);\n"
s = sub1(s, re.escape(OLD), NEW, "bank listing")

# 6) the oracle, right after the gunzip that produced the bytes it hashes
OLD = (T + T + T + T + "tb_logv(\"GUNZIP\", (ulong)(unsigned int)rc);\n"
       + T + T + T + T + "tb_logv(\"SRC USED\", srclen);\n")
NEW = (OLD
       + "\n"
       + T + T + T + T + "if (!rc) {\n"
       + T + T + T + T + T + "u64 k8 = tb_ram_rd64(kload);\n"
       + T + T + T + T + T + "u32 got;\n"
       + "\n"
       + T + T + T + T + T + "/* The image's first word is efi_signature_nop\n"
       + T + T + T + T + T + " * (0xfa405a4d), then the branch to primary_entry. */\n"
       + T + T + T + T + T + "tb_logv2(\"K8\", (ulong)(u32)k8, (ulong)(u32)(k8 >> 32));\n"
       + T + T + T + T + T + "got = tb_fnv1a32(kload, TB_ORACLE_LEN);\n"
       + T + T + T + T + T + "tb_logv2(\"ORCL\", (ulong)got, TB_ORACLE_FNV);\n"
       + T + T + T + T + "}\n")
s = sub1(s, re.escape(OLD), NEW, "oracle")

# 7) the ladder is gone; keep only printk's write pointer, which is the one
#    reading that says whether the kernel ever formatted a line.
OLD_PAT = (r"\t\t\t\t\t/\* What the previous boot's kernel left,\n"
           r"[\s\S]*?tb_logv\(\"PRV RB BITS\", bits\);\n")
NEW_PRV = (T + T + T + T + T + "/* head_lpos: printk's write pointer. At its\n"
           + T + T + T + T + T + " * initial value not one line was formatted. */\n"
           + T + T + T + T + T + "tb_logv(\"PRV HEAD\", head);\n"
           + T + T + T + T + T + "tb_logv(\"PRV DVA\", dva);\n")
s = sub1(s, OLD_PAT, NEW_PRV, "PRV ladder")

# 8) only dump the ring when the write pointer says printk ran; with an empty
#    ring this printed non-printable bytes over the diagnostics above it.
OLD = (T + T + T + T + T + "if (dva >= TB_KERNEL_TEXT_VA &&\n"
       + T + T + T + T + T + "    bits >= 12 && bits <= 24) {\n")
NEW = (T + T + T + T + T + "if (dva >= TB_KERNEL_TEXT_VA &&\n"
       + T + T + T + T + T + "    bits >= 12 && bits <= 24 && head >= 0x1000 &&\n"
       + T + T + T + T + T + "    head < 0x4000000) {\n")
s = sub1(s, re.escape(OLD), NEW, "ring guard")

# 9) bookkeeping lines with nothing left to say
for line in ['tb_logv("KPART", (ulong)(unsigned int)rc);\n',
             'tb_logv("MEM SIZE", (ulong)gd->ram_size);\n',
             'tb_logv("UB RELOC", (ulong)gd->relocaddr);\n',
             'tb_logv("KLOAD", kload);\n',
             'tb_logv("DTB PART", (ulong)(unsigned int)rc);\n',
             'tb_logv("DTB READ", (ulong)(unsigned int)brc);\n',
             'tb_logv("ARGS SET", (ulong)(unsigned int)\n',
             'tb_logv("UART DISABLED", 1);\n']:
    if line.endswith("\n") and line.startswith('tb_logv("ARGS SET"'):
        pat = (r"\t\t\t\ttb_logv\(\"ARGS SET\", \(ulong\)\(unsigned int\)\n"
               r"\t\t\t\t\tfdt_setprop_string\(fdt, off, \"bootargs\",\n"
               r"[\s\S]*?clk_ignore_unused pd_ignore_unused\"\)\);\n")
        s = sub1(s, pat, "", "drop ARGS SET")
        continue
    pat = r"[ \t]*" + re.escape(line)
    s = sub1(s, pat, "", "drop " + line.strip()[:24])

# 10) U-Boot's canaries, written last so the next boot's reading is this boot's
#     store surviving XBL and the reset, and read back here to prove the store
#     and load paths agree at all.
OLD = (T + T + T + "{\n"
       + T + T + T + T + "ulong entry = kload;\n")
NEW = (T + T + T + "tb_ram_wr64(TB_PRB1 + TB_PRB_OFF, 0xc0de0001UL);\n"
       + T + T + T + "tb_ram_wr64(TB_PRB2 + TB_PRB_OFF, 0xc0de0002UL);\n"
       + T + T + T + "tb_ram_wr64(TB_PRB3 + TB_PRB_OFF, 0xc0de0003UL);\n"
       + T + T + T + "tb_logv(\"RT1\", tb_ram_rd64(TB_PRB1 + TB_PRB_OFF));\n"
       + T + T + T + "tb_logv(\"RT2\", tb_ram_rd64(TB_PRB2 + TB_PRB_OFF));\n"
       + T + T + T + "tb_logv(\"RT3\", tb_ram_rd64(TB_PRB3 + TB_PRB_OFF));\n"
       + "\n" + OLD)
s = sub1(s, re.escape(OLD), NEW, "canary writes")

io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: measurement channel instrumented")
print("initcall.c: tb_logv2() added")
