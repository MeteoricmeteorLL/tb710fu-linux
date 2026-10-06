#!/usr/bin/env python3
"""TB710FU U-Boot build #14 - stop drawing during the F sequence.

Everything in the fixup loop is verified safe: bounds correct, guard intact, the
destination-end store present, the table spans the right 4738 entries, and the
destination region is writable (the 1.24 MiB copy wrote it). A full power cycle
changed nothing, so it is not a damaged hardware state. What fits every
observation - a stall at a similar iteration count across builds with different
layouts and destinations, and a boot that sometimes finished the whole loop - is
the watchdog cutting the CPU at a fixed time after XBL armed it, with the window
varying per boot depending on how long XBL/ABL took.

The dominant cost before relocation is tb_progress(): it redraws a 714x144 pixel
"index:address" marker for every one of the ~66 F-sequence entries, i.e. about
27 MiB of strongly ordered framebuffer stores, which the earlier build only
trimmed around the edges. Drop that drawing entirely (the RAM marker stays), and
drop the opening panel wipe. The log after relocation is what we actually read.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) lib/initcall.c: tb_progress draws nothing ------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

start = s.index("\t{\n\t\tstatic const int tb_strides[] = { 3200, 2000 };")
end = s.index("\tidx++;\n}", start)
new = """\t/* TB710FU: the on-screen marker was removed. It redrew a 714x144 pixel
	 * "index:address" string for every F-sequence entry - about 27 MiB of
	 * strongly ordered framebuffer stores before relocation - and that alone
	 * was enough to run the boot past the watchdog window, which is what made
	 * the relocation look flaky. The RAM marker above still records the
	 * sequence, and lib/initcall.c's text log is the channel used for reading
	 * state off the screen.
	 */
"""
s = s[:start] + new + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: tb_progress no longer draws")

# --- 2) board_f.c: drop the panel wipe as well --------------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
start = s.index("\t/* 1) TB710FU: the previous full-panel wipe wrote 25.6 MiB")
end = s.index("\t/* 2) green banner")
s = s[:start] + """\t/* 1) TB710FU: no panel wipe. Even this narrowed version wrote 12 MiB of
	 * strongly ordered stores before relocation; the log below clears its own
	 * line before drawing, so leftovers from the previous boot do not matter.
	 * Anything dug into the screen must fit the watchdog window.
	 */
""" + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: panel wipe removed")
