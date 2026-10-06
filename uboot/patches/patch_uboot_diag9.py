#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #9 - stop swallowing errors in the R loop.

Status: relocation now completes and board_init_r runs (the red sentinel and the
on-screen log both prove it). The log reports VIDEO FAIL and UFS FAIL, both
-ENODEV, i.e. the two uclasses are empty - yet the appended DTB is intact and
sits exactly at _end (magic at 0x14B458, totalsize 108440), and CONFIG_OF_BOARD
plus CONFIG_OF_SEPARATE mean that is the DT U-Boot uses.

The hand-rolled loop does `if (fn()) break;`, so a failing initcall (initr_of_live
is a prime suspect: CONFIG_OF_LIVE=y, and if the live tree is not built the DM
scan binds nothing) stops the loop silently. Print the last entry attempted and
its return code, plus the DT facts, so the next screen photo says exactly which
step fails.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) board_r.c: instrument the R loop and dump DT facts ---------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

if "#include <linux/libfdt.h>" not in s:
    anchor = "#include <scsi.h>"
    assert anchor in s
    s = s.replace(anchor, anchor + "\n#include <linux/libfdt.h>", 1)

old = """	{
		int i;

		for (i = 0; i < 14; i++) {
			init_fnc_t fn = init_sequence_r[i];

			if (!fn || ((ulong)fn & INITCALL_IS_EVENT))
				continue;

			/* Rewritten every iteration: the last value left on screen
			 * names the entry that hangs. */
			tb_screen_fixed_hex(420, (ulong)i, 5);
			tb_screen_fixed_hex(520, (ulong)fn, 4);
			if (fn())
				break;
		}
	}
"""
new = """	{
		int i, rc = 0, last = -1;

		for (i = 0; i < 14; i++) {
			init_fnc_t fn = init_sequence_r[i];

			if (!fn || ((ulong)fn & INITCALL_IS_EVENT))
				continue;
			last = i;
			/* Rewritten every iteration so a hang still leaves the
			 * index of the entry that hung on screen. */
			tb_screen_fixed_hex(1000, (ulong)i, 5);
			rc = fn();
			if (rc)
				break;
		}

		/* High half = last entry attempted, low half = its return code. */
		tb_screen_log_reset();
		tb_screen_log("R LAST AND RC", 5);
		tb_screen_log_hex((ulong)(((unsigned)last << 16) |
					  ((unsigned)rc & 0xffff)), 4);
	}
"""
assert s.count(old) == 1, ("R loop anchor", s.count(old))
s = s.replace(old, new, 1)

old = """	tb_screen_log_reset();
	tb_screen_log("TB710FU DIAG4", 5);
"""
new = """	tb_screen_log("TB710FU DIAG9", 5);

	/* Which device tree is in use, and does it carry the framebuffer node the
	 * video console needs? fdt_src 2 = board hook, 5 = separate (appended). */
	tb_screen_log("FDT SRC", 5);
	tb_screen_log_hex((ulong)gd->fdt_src, 4);
	tb_screen_log("FDT SIZE", 5);
	tb_screen_log_hex((ulong)fdt_totalsize(gd->fdt_blob), 4);
	tb_screen_log("FDT BLOB", 5);
	tb_screen_log_hex((ulong)(uintptr_t)gd->fdt_blob, 4);
	tb_screen_log("FB NODE FOUND", 5);
	tb_screen_log_hex((ulong)(ofnode_valid(ofnode_by_compatible(
			ofnode_null(), "simple-framebuffer")) ? 1 : 0), 4);
"""
assert s.count(old) == 1, ("log head anchor", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: R loop instrumented, DT facts printed")

# --- 2) drop the assembly marks: relocation is proven, they only add noise -
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
print("initcall.c untouched (tb_mark stays, now unused by the .S files)")

p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
n = s.count("bl\ttb_mark")
print("relocate_64.S still has %d mark call sites (left in place)" % n)
