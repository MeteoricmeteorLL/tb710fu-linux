#!/usr/bin/env python3
"""Build #37 (memboot9): no kernel, so the canary measures DRAM, not the kernel.

v8 tried to separate "the kernel cleared .bss" from "the reset wiped DRAM" with a
control canary 512 MiB above the load address. It did not survive either, but
0xC8000000 may simply sit in one of XBL's carveouts, so it is not a control.
The .bss window showed 95,283 zero words out of 103,488, which is what the
kernel's PI-stub memset produces - but every boot so far had a kernel in it, so
that reading cannot be attributed either.

Remove the kernel from the experiment: write both canaries, log, and hang
instead of jumping. The next boot then reads memory that nothing but XBL and the
reset could have touched:

  canary mostly intact -> DRAM survives the reset and DDR training leaves it
                          alone: the post-mortem channel is valid, and every
                          "the kernel left this" reading in this session holds
  canary gone too      -> DRAM does not survive, the channel is void, and the
                          kernel log has to be written somewhere readable
                          (a partition, pulled from Android over adb) instead
"""
import io

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = '''			tb_probe_dump(2);

			tb_screen_log("JUMP", 3);'''
new = '''			tb_probe_dump(2);

			/* Control run: no kernel, so the next boot's canary
			 * readings measure DRAM and the reset alone. */
			tb_screen_log("CONTROL RUN", 3);
			hang();

			tb_screen_log("JUMP", 3);'''
assert s.count(old) == 1, ("nojump", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: control run - canaries written, no jump")
