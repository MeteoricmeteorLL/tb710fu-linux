#!/usr/bin/env python3
"""Hand the kernel an initramfs, so init has something to exec.

The panel console showed the kernel getting all the way to user space and then
dying there: Attempted to kill init, exitcode SIGSEGV - because there is no
/init anywhere for it to run. The kernel has nothing to mount and nothing to
exec, so the last thing it does is panic.

The initramfs lives in the same partition as the kernel, right after the 16 MiB
area U-Boot already reads the kernel from, and U-Boot reads it out and passes it
through /chosen as linux,initrd-start / linux,initrd-end. That is the interface
mainline arm64 documents; no kernel change is needed.

  recovery_b:  [0, 16 MiB)         gzipped kernel   (read as before)
               [16 MiB, 16 MiB+n)  initramfs        (read here, -> 0xAD000000)

0xAD000000 is inside /memory (the SMEM banks run from 0xAC400000 upward) and
above XBL's ramoops reservation at 0xAC300000, so nothing else is using it.
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


# 1) the two facts the DTB block needs, at routine scope
sub1(re.escape(T + T + "ulong srclen = 0;\n"),
     T + T + "ulong srclen = 0;\n"
     + T + T + "ulong ir_start = 0, ir_len = 0;\t/* initramfs, from /chosen */\n",
     "ir locals")

# 2) read the initramfs next to the kernel, from the same partition
sub1(re.escape(T + T + T + "if (!rc) {\n"
               + T + T + T + T + "srclen = 0x1000000;\n"),
     T + T + T + "/* TB710FU: the initramfs sits right after the 16 MiB the\n"
     + T + T + T + " * kernel was read from. Without it the kernel reaches user\n"
     + T + T + T + " * space with nothing to exec and panics: Attempted to kill\n"
     + T + T + T + " * init. */\n"
     + T + T + T + "if (!rc) {\n"
     + T + T + T + T + "brc = blk_dread(kdesc, kinfo.start + 0x8000, 0x1000,\n"
     + T + T + T + T + T + T + "\t(void *)0xad000000UL);\n"
     + T + T + T + T + "tb_logv(\"INITRD READ\", (ulong)(unsigned int)brc);\n"
     + T + T + T + T + "if (brc != 0x1000)\n"
     + T + T + T + T + T + "rc = -EIO;\n"
     + T + T + T + T + "else {\n"
     + T + T + T + T + T + "ir_start = 0xad000000UL;\n"
     + T + T + T + T + T + "ir_len = 1046178UL;\t/* the initramfs file */\n"
     + T + T + T + T + "}\n"
     + T + T + T + "}\n"
     "\n"
     + T + T + T + "if (!rc) {\n"
     + T + T + T + T + "srclen = 0x1000000;\n",
     "read initramfs")

# 3) pass it through /chosen
sub1(re.escape(T + T + T + T + "fdt_setprop_string(fdt, off, \"bootargs\",\n"),
     T + T + T + T + "if (ir_start) {\n"
     + T + T + T + T + T + "u64 iv[2];\n"
     "\n"
     + T + T + T + T + T + "iv[0] = cpu_to_fdt64(ir_start);\n"
     + T + T + T + T + T + "iv[1] = cpu_to_fdt64(ir_start + ir_len);\n"
     + T + T + T + T + T + "fdt_setprop(fdt, off, \"linux,initrd-start\",\n"
     + T + T + T + T + T + T + "\t    &iv[0], 8);\n"
     + T + T + T + T + T + "fdt_setprop(fdt, off, \"linux,initrd-end\",\n"
     + T + T + T + T + T + T + "\t    &iv[1], 8);\n"
     + T + T + T + T + "}\n"
     + T + T + T + T + "tb_logv(\"INITRD LEN\", ir_len);\n"
     + T + T + T + T + "fdt_setprop_string(fdt, off, \"bootargs\",\n",
     "chosen initrd")

io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("ok: initramfs read + /chosen wiring installed")
