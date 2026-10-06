#!/usr/bin/env python3
"""TB710FU U-Boot build #24 - wrap the log, keep the latest lines on screen.

Build #23's log shows the driver model now works: DM_INIT, DM_SCAN_FDT and
DM_SCAN_OTHER all return 0 with CONFIG_OF_LIVE off, and the timer probe fails
harmlessly (there is no DM timer device on this board). That is exactly the
"bind without probing" the storage path needs.

Problem: the log draws downwards at 68 pixels per line from row 420, so after
about 23 calls it runs off the 2000-row panel - and the lines we care about
now (PROBE UFS, UFS OK/FAIL, SCSI COUNT) are the ones that fall off. So:

  * tb_screen_log wraps back to the top instead of running off the bottom, so
    the newest lines are always the ones on screen;
  * the per-entry address logging in tb_progress is switched off - it named the
    entry that hung, which is done, and it was costing ten lines of screen.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) wrap the log cursor ----------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """	tb_fb_clear_at(TB_LOG_X, tb_log_y, 800,
		       16 * scale + 8, TB_LOG_STRIDE, 1);
	tb_screen_text(TB_LOG_X, tb_log_y, buf, scale);
	tb_log_y += 16 * scale + 20;
}"""
new = """	tb_fb_clear_at(TB_LOG_X, tb_log_y, 800,
		       16 * scale + 8, TB_LOG_STRIDE, 1);
	tb_screen_text(TB_LOG_X, tb_log_y, buf, scale);
	tb_log_y += 16 * scale + 20;

	/* Wrap instead of running off the bottom of the panel: the lines worth
	 * reading are the newest ones, and a 2000-row screen only holds about 23
	 * of them at this pitch. */
	if (tb_log_y > 1900)
		tb_log_y = TB_LOG_TOP;
}"""
assert s.count(old) == 1, ("log fn tail", s.count(old))
s = s.replace(old, new, 1)

# --- 2) stop logging every R-sequence entry address ----------------------
old = """	if (gd->flags & GD_FLG_RELOC) {
		char abuf[9];
		char *q = abuf;

		tb_put_hex(&q, (ulong)func, 8);
		*q = 0;
		tb_screen_log(abuf, 3);
	}
"""
new = """	/* TB710FU: the per-entry address log is off. It identified the entry that
	 * hung (initr_dm), which is done, and its ten lines crowded the screen. */
"""
assert s.count(old) == 1, ("address log", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: log wraps, entry-address log removed")
