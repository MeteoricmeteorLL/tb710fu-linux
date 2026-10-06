#!/usr/bin/env python3
"""TB710FU U-Boot build #10 - make the R sequence actually run.

Root cause of VIDEO FAIL / UFS FAIL: the hand-rolled loop inherited from the
earlier session tested `(ulong)fn & INITCALL_IS_EVENT`, but INITCALL_IS_EVENT is
GENMASK(BITS_PER_LONG - 1, 8) - a mask that every normal function pointer has
bits in - so all 14 entries were skipped and initr_dm never ran. The DM scan
never happened, so no device was ever bound and both uclasses were empty. That
also explains the ffff0000 (last = -1) reading.

Fix: truncate init_sequence_r at initr_dm_devices (dm_autoprobe() hangs probing
unrelated drivers) into a local array and run it through the real
initcall_run_list(), which understands the encoding, the event entries and the
relocation offset. Devices we need are still probed explicitly afterwards.

Also try to disarm the APPS watchdog XBL leaves armed: nothing in U-Boot feeds
it, which is why the session dies after a few tens of seconds.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) board_r.c: run the truncated sequence properly -------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """	{
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
new = """	/* TB710FU: run the real init sequence, but only the part before
	 * initr_dm_devices. That entry calls dm_autoprobe(), which hangs probing
	 * unrelated drivers; what we actually need is probed explicitly below.
	 *
	 * initcall_run_list() is used rather than a hand-rolled loop because the
	 * array holds encoded event entries as well as function pointers
	 * (INITCALL_IS_EVENT is a mask over bits 8..63, so testing a function
	 * pointer against it is never false), and because it applies the
	 * relocation offset itself.
	 */
	{
		init_fnc_t seq[64];
		int i, n = 0, rc;

		for (i = 0; i < 63 && init_sequence_r[i]; i++) {
			if (init_sequence_r[i] == (init_fnc_t)initr_dm_devices)
				break;
			seq[n++] = init_sequence_r[i];
		}
		seq[n] = NULL;

		tb_screen_log_reset();
		tb_screen_log("TB710FU DIAG10", 5);
		tb_screen_log("R ENTRIES BEFORE DM DEV", 5);
		tb_screen_log_hex((ulong)n, 4);

		rc = initcall_run_list(seq);
		tb_screen_log(rc ? "R SEQ FAIL" : "R SEQ OK", 5);
		tb_screen_log_hex((ulong)(unsigned int)rc, 4);
	}
"""
assert s.count(old) == 1, ("R loop anchor", s.count(old))
s = s.replace(old, new, 1)

old = """	tb_screen_log("TB710FU DIAG9", 5);
"""
new = ""
assert s.count(old) == 1, ("diag9 head", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: R sequence now runs through initcall_run_list()")

# --- 2) board_f.c: try to disarm the APPS watchdog ----------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "TB710FU_WDT" not in s
anchor = "void board_init_f(ulong boot_flags)\n{\n\ttb_banner_early();"
assert s.count(anchor) == 1
new = anchor + """
	/* TB710FU: XBL leaves the APPS watchdog armed and nothing in U-Boot
	 * feeds it, so this session is killed after a few tens of seconds.
	 * Clear the enable bit; the two layouts below cover the variants seen on
	 * these SoCs (plain and the one needing the 0x51F15E key). */
	{
		void *wdt = (void *)0x17C10000UL;

		writel(0x51F15E, wdt + 0x8);	/* secure kdog: disarm key */
		writel(0, wdt + 0x8);		/* WDT_EN */
		writel(0, wdt + 0x4);		/* WDT_RST */
	}"""
s = s.replace(anchor, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: watchdog disarm attempt added")
