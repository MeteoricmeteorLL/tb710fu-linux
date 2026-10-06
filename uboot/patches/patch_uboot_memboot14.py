#!/usr/bin/env python3
"""Build #40 (memboot14): read the leftovers before the gunzip overwrites them.

v13 finally produced trustworthy readings, and they say two things:

  * the read channel is exact - a FNV-1a-32 over a megabyte of the loaded kernel
    came back equal to the value computed offline from the flashed file, and the
    image header's first two words matched to the bit;
  * U-Boot runs at EL1 with the MMU off (SCTLR_EL1 = 0x30d00988, M=0), so the
    physical addressing this project assumes is real.

What they also exposed is a measurement bug that invalidates the whole ladder
this session has been reading. boot_args (0x2395000), idmap_pg_dir (0x2010000),
kimage_voffset (0x1f74000) and printk_rb_static (0x23b4498) all sit BELOW
srclen = 0x2915a00, the length of the gunzipped image - and the routine gunzips
into kload and only then reads them. So every "the previous kernel left this"
reading was actually reading the file's own bytes, freshly written by this
boot's gunzip. boot_args read 0 because the file says 0.

Only .bss (0x2916000) and __log_buf (0x292c170) sit above srclen, and those read
nonzero (0x0a0b2058, 0xa0000000), which is the kernel having written them.

So this build:

  1. Reads every previous-boot value at the TOP of the routine, before the
     partition read and the gunzip. The ladder then means what it was always
     supposed to mean, and boot_args[0] becomes the authoritative measurement of
     what x0 the kernel actually received - no stub involved.

  2. Drops the stub entirely. Its record was written at 0x8f000000 and later
     0xaaa00000, and both come back across a reset as 0xffffffff with a handful
     of bits decayed - DRAM outside the region XBL keeps for the kernel. The
     stub's readings were never valid; boot_args is in the kernel image area,
     which the v9 control run proved retains.

  3. Moves its canaries into the one gap that nothing writes: the linker padding
     between the end of the image file (0x2915a00) and __bss_start (0x2916000),
     i.e. 0xaa915a00 - 0xaa916000. It is not in the file, not in .bss, not
     written by the gunzip, not covered by the kernel's memset, and inside the
     region the control run proved. Two more canaries at 0xaa9e1000 (just past
     the image) and 0x8f000000 (the address that never retained) locate the
     boundary of the memory that does.

  4. Dumps printk's text ring when its write pointer has moved off the initial
     value - the kernel's own last words, straight off the panel.
"""
import io
import re

P = "/home/meteor/u-boot-13r/common/board_r.c"
T = "\t"

s = io.open(P, encoding="utf-8", errors="surrogateescape").read()


def sub1(pat, rep, name):
    global s
    new, n = re.subn(pat, lambda m: rep, s, count=1)
    assert n == 1, ("EDIT FAILED: " + name, n)
    s = new


# ---------------------------------------------------------------------------
# 1) probe addresses, and the printk ring's initial logical position
# ---------------------------------------------------------------------------
OLD = (
    "/* Hand-off probe: scratch record and where to copy the stub. Just past the end\n"
    " * of the kernel image, in the region the v9 control run proved survives a\n"
    " * reset, and clear of the image, the raw tree and the compressed kernel. */\n"
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
)
NEW = (
    "/* Canary addresses. The gap at 0xaa915a00 is the linker's own padding between\n"
    " * the end of the image file (0x2915a00) and __bss_start (0x2916000): it is not\n"
    " * in the file, not in .bss, not written by the gunzip, not covered by the\n"
    " * kernel's later memset, and inside the region the v9 control run proved comes\n"
    " * back through a reset. 0xaa9e1000 is just past the image; 0x8f000000 is the\n"
    " * address the stub's record lived at and never retained. */\n"
    "#define TB_PRB_GAP" + T + T + "0xaa915a40UL\n"
    "#define TB_PRB_POST" + T + T + "0xaa9e1000UL\n"
    "#define TB_PRB_OLD" + T + T + "0x8f000000UL\n"
    "\n"
    "/* printk's head_lpos at link time: -(1 << 17), the text ring's size. Any other\n"
    " * value means printk advanced it, i.e. it formatted a record. */\n"
    "#define TB_LOG_LPOS_INIT" + T + "0xfffffffffffe0000ULL\n"
)
sub1(re.escape(OLD), NEW, "probe addresses")

# ---------------------------------------------------------------------------
# 2) the stub is gone
# ---------------------------------------------------------------------------
sub1(r"/\* Assembled from mainline-kernel/stub-handoff\.S[\s\S]*?\n\};\n\n",
     "", "stub array")

# ---------------------------------------------------------------------------
# 3) read the leftovers first, before anything this boot can overwrite them
# ---------------------------------------------------------------------------
OLD_PAT = (r"\t\ttb_logv\(\"UB EL\"[\s\S]*?tb_ram_rd64\(TB_STUB_SCRATCH \+ 16\)\);\n")
NEW_TOP = (
    T + T + 'tb_logv("UB EL", (ulong)current_el());\n'
    + T + T + 'tb_logv("UB SCTLR", get_sctlr());\n'
    "\n"
    + T + T + "/* What the previous boot left, read HERE: every address below the\n"
    + T + T + " * gunzip's output length (0x2915a00) is about to be overwritten\n"
    + T + T + " * with the file's own bytes, which is precisely what the old\n"
    + T + T + " * ladder was reading. boot_args is the one that matters - the\n"
    + T + T + " * kernel stores x0..x3 there in its second instruction, so it is\n"
    + T + T + " * x0 at entry, measured by the kernel itself. */\n"
    + T + T + 'tb_logv2("PREV BA", tb_ram_rd64(kload + TB_K_BOOT_ARGS),\n'
    + T + T + T + " tb_ram_rd64(kload + TB_K_BOOT_ARGS + 8));\n"
    + T + T + 'tb_logv("PREV VOFF", tb_ram_rd64(kload + TB_K_KIMAGE_VOFFSET));\n'
    + T + T + 'tb_logv2("PREV BSS", tb_ram_rd64(kload + TB_K_BSS_START),\n'
    + T + T + T + " tb_ram_rd64(kload + TB_K_LOG_BUF));\n"
    "\n"
    + T + T + "/* 0xaa915a40 is in the padding gap, so what it holds is what\n"
    + T + T + " * the previous boot stored there and nothing else. */\n"
    + T + T + 'tb_logv("C1", tb_ram_rd64(TB_PRB_GAP));\n'
    + T + T + 'tb_logv("C2", tb_ram_rd64(TB_PRB_POST));\n'
    + T + T + 'tb_logv("C3", tb_ram_rd64(TB_PRB_OLD));\n'
    "\n"
    + T + T + "{\n"
    + T + T + T + "u64 h = tb_ram_rd64(kload + TB_LOG_RB_OFF +\n"
    + T + T + T + T + T + T + "TB_LOG_RB_HEAD);\n"
    + T + T + T + "u32 bits = (u32)tb_ram_rd64(kload + TB_LOG_RB_OFF +\n"
    + T + T + T + T + T + T + "TB_LOG_RB_SIZEBITS);\n"
    "\n"
    + T + T + T + 'tb_logv2("PREV HLPS", (ulong)(u32)h, (ulong)(u32)(h >> 32));\n'
    "\n"
    + T + T + T + "/* The text ring sits above the gunzip's output, so nothing\n"
    + T + T + T + " * this boot has written can have reached it yet. */\n"
    + T + T + T + "if (h != TB_LOG_LPOS_INIT && bits >= 12 && bits <= 24) {\n"
    + T + T + T + T + "ulong size = 1UL << bits;\n"
    "\n"
    + T + T + T + T + "tb_ram_text_ring(kload + TB_K_LOG_BUF, size,\n"
    + T + T + T + T + T + T + " ((ulong)h + size - 400) & (size - 1),\n"
    + T + T + T + T + T + T + " 400);\n"
    + T + T + T + T + "tb_probe_dump(2);\n"
    + T + T + T + "}\n"
    + T + T + "}\n"
)
sub1(OLD_PAT, NEW_TOP, "previous-boot reads at the top")

# ---------------------------------------------------------------------------
# 4) the ladder after the gunzip is meaningless now, and 'img' with it
# ---------------------------------------------------------------------------
sub1(re.escape(T + T + T + T + "ulong img;\n\n" + T + T + T + T
               + "srclen = 0x1000000;\n"),
     T + T + T + T + "srclen = 0x1000000;\n", "drop img")

sub1(r"\n\t\t\t\t/\* The load stopped at srclen[\s\S]*?\n\t\t\t\t\}\n(?=\t\t\t\})",
     "\n", "drop post-gunzip ladder")

# ---------------------------------------------------------------------------
# 5) canaries in the gap, the stub branch gone, JUMP on its own
# ---------------------------------------------------------------------------
OLD_PAT_CANARY = (r"\t\t\ttb_probe_dump\(2\);\n"
                  r"[\s\S]*?"
                  r"armv8_switch_to_el2\(\(u64\)kfdt, 0, 0, 0,\n"
                  r"[\s\S]*?ES_TO_AARCH64\);\n"
                  r"\t\t\t\}\n")
NEW = (T + T + T + "tb_ram_wr64(TB_PRB_GAP, 0xc0de0001UL);\n"
       + T + T + T + "tb_ram_wr64(TB_PRB_POST, 0xc0de0002UL);\n"
       + T + T + T + "tb_ram_wr64(TB_PRB_OLD, 0xc0de0003UL);\n"
       + T + T + T + "tb_logv(\"RT1\", tb_ram_rd64(TB_PRB_GAP));\n"
       + T + T + T + "tb_logv(\"RT2\", tb_ram_rd64(TB_PRB_POST));\n"
       + T + T + T + "tb_logv(\"RT3\", tb_ram_rd64(TB_PRB_OLD));\n"
       "\n"
       + T + T + T + "tb_screen_log(\"JUMP\", 3);\n"
       "\n"
       + T + T + T + "/* U-Boot runs with whatever cache state the bootloader\n"
       + T + T + T + " * left; stale instruction lines over the payload would\n"
       + T + T + T + " * run old code. */\n"
       + T + T + T + "icache_disable();\n"
       + T + T + T + "invalidate_icache_all();\n"
       "\n"
       + T + T + T + "/* The hand-off bootm makes, without the command\n"
       + T + T + T + " * interpreter, the environment or the image machinery,\n"
       + T + T + T + " * none of which this board's bring-up sets up. */\n"
       + T + T + T + "cleanup_before_linux();\n"
       + T + T + T + "armv8_switch_to_el2((u64)kfdt, 0, 0, 0, (u64)kload,\n"
       + T + T + T + T + T + "    ES_TO_AARCH64);\n")
sub1(OLD_PAT_CANARY, NEW, "canaries + jump")

io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: v14 - leftovers read before the gunzip, stub dropped")
