#!/usr/bin/env python3
"""TB710FU U-Boot build #13 - cut the framebuffer cost so the boot fits in the
watchdog window.

The relocation fixup loop is provably safe (guarded writes inside a region the
copy loop just wrote, table reads inside the image), yet it sometimes stops
around entry 320 and sometimes finishes. The tell is the watchdog: this board's
watchdog is Gunyah/XBL-managed (writing 0x17C10000 hangs the bus, so it can
neither be disarmed nor fed from U-Boot), and the window left for us depends on
how long XBL/ABL took. Meanwhile this build writes tens of megabytes to the
splash framebuffer on every boot: a full 3200x2000 wipe, a 3168 px wide clear
per log line, 2700 px wide marker bars. Strongly-ordered framebuffer stores are
slow, so the boot regularly runs past the window.

Changes: drop the full-panel wipe and the previous-session marker render, narrow
the log clear to 800 px and its scale to 3, narrow the marker bars to 600 px,
and print the runtime address of board_init_f (that plus its link address from
nm gives the load address, which is still unknown).
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) board_f.c: no full wipe, no marker render, print load-address proof --
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """	/* 1) wipe the whole panel so nothing from a previous boot remains */
	for (row = 0; row < 2000; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 3200; col++)
			line[col] = 0xFF000000;
	}

"""
new = """	/* 1) TB710FU: the previous full-panel wipe wrote 25.6 MiB on every boot
	 * and helped push the boot past the watchdog window, so only the area the
	 * log actually uses is cleared now (rows 0..1900, the left half). */
	for (row = 0; row < 1900; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 1600; col++)
			line[col] = 0xFF000000;
	}

"""
assert s.count(old) == 1, ("wipe anchor", s.count(old))
s = s.replace(old, new, 1)

# drop the previous-session marker render (reads junk RAM on a cold boot)
start = s.index("\t/*\n\t * TB710FU: render the PREVIOUS session's last initcall markers")
end = s.index("\t}\n}\n\nvoid board_init_f", start)
s = s[:start] + "\t/* TB710FU: the previous-session marker render was dropped: it read\n\t * 0x9b09c000 (junk on a cold boot) and cost time the watchdog does not\n\t * give back. */\n" + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: wipe narrowed, marker render removed")

# --- 2) narrow marker bars and log clears ---------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		for (c = 0; c < 2700; c++)
			line[c] = col;"""
new = """		for (c = 0; c < 600; c++)
			line[c] = col;"""
assert s.count(old) == 1, ("bar width", s.count(old))
s = s.replace(old, new, 1)

old = """	tb_fb_clear_at(TB_LOG_X, tb_log_y, TB_LOG_STRIDE - 32,
		       16 * scale + 8, TB_LOG_STRIDE, 1);"""
new = """	tb_fb_clear_at(TB_LOG_X, tb_log_y, 800,
		       16 * scale + 8, TB_LOG_STRIDE, 1);"""
assert s.count(old) == 1, ("log clear width", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: bars 600 px, log clear 800 px")

# --- 3) board_r.c: log at scale 3, print board_init_f's runtime address ----
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = '''		tb_screen_log("TB710FU DIAG10", 5);'''
new = '''		extern void board_init_f(ulong);
		tb_screen_log("TB710FU DIAG13", 3);'''
assert s.count(old) == 1, ("diag string", s.count(old))
s = s.replace(old, new, 1)

# scale 5 -> 3 for the whole log sequence
s = s.replace(', 5);', ', 3);')
old = '''	tb_screen_log("FDT SRC", 3);'''
new = '''	tb_screen_log("FDT SRC", 3);
	tb_screen_log("LOAD ADDR PROOF", 3);
	tb_screen_log_hex((ulong)(uintptr_t)&board_init_f, 3);'''
assert s.count(old) == 1, ("fdt src anchor", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: log at scale 3, board_init_f address printed")
