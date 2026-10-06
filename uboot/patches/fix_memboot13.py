#!/usr/bin/env python3
"""Fixups for build #39 after reviewing the v13 diff.

1. The ARGS SET line was tb_logv() wrapped *around* the fdt_setprop_string()
   that writes bootargs, so dropping the log line dropped the bootargs too.
   Put the store back without the logging.

2. The comment above the probe addresses still described the old location of
   the stub.
"""
import io
import re

P = "/home/meteor/u-boot-13r/common/board_r.c"
T = "\t"

s = io.open(P, encoding="utf-8", errors="surrogateescape").read()


def sub1(pat, rep, name):
    global s
    new, n = re.subn(pat, lambda m: rep, s, count=1)
    assert n == 1, ("FIXUP FAILED: " + name, n)
    s = new


# 1) bootargs must still be written into /chosen
OLD = (T + T + T + T + "fdt_delprop(fdt, off, \"stdout-path\");\n"
       + T + T + T + "}\n")
NEW = (T + T + T + T + "fdt_delprop(fdt, off, \"stdout-path\");\n"
       + T + T + T + T + "fdt_setprop_string(fdt, off, \"bootargs\",\n"
       + T + T + T + T + T + "\"console=tty0 loglevel=8 \"\n"
       + T + T + T + T + T + "\"ignore_loglevel nokaslr \"\n"
       + T + T + T + T + T + "\"clk_ignore_unused pd_ignore_unused\");\n"
       + T + T + T + "}\n")
sub1(re.escape(OLD), NEW, "bootargs restored")

# 2) the probe comment
OLD = ("""/* Hand-off probe: scratch record and where to copy the stub. Plain DRAM below
 * the firmware carveouts, outside everything this boot reads or writes. */""")
NEW = ("""/* Hand-off probe: scratch record and where to copy the stub. Just past the end
 * of the kernel image, in the region the v9 control run proved survives a
 * reset, and clear of the image, the raw tree and the compressed kernel. */""")
sub1(re.escape(OLD), NEW, "probe comment")

io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: bootargs store restored, probe comment updated")
