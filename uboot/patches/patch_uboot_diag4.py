#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #4 - localise the F->R boundary hang.

Evidence from diag3: the banner, the tb_progress marker (last index 0x31 = the
last F entry) and board_f's yellow "F sequence returned" block were all drawn,
but nothing from board_init_r appeared. So execution dies between the end of
board_init_f and the first R initcall - i.e. in the crt0 relocate_code path.

Single variable: diag3's only other change was the DTS framebuffer geometry
(reg 1 MiB -> 5 MiB, width 640 -> 3200). Revert it: the U-Boot console is not
needed, our own big-text renderer is the logging channel.

Instrumentation (three unambiguous sentinels):
  YELLOW (already there) = init_sequence_f returned
  BLUE   = board_init_f tail reached after the yellow block
  RED    = first statement of board_init_r (so relocation+hand-off worked)
and inside the R loop the current index and function address are redrawn at a
fixed row, so the last one visible names the entry that hangs.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) revert the DTS framebuffer geometry to the diag2 values -------------
p = U + "dts/upstream/src/arm64/qcom/sm8650-lenovo-tb710fu.dts"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		/* simplefb derives the row pitch from "width", so it has to match the
		 * panel (3200) or every console line shears across the screen. "height"
		 * only caps how many rows the console may use, and "reg" has to cover
		 * width * height * 4 bytes. */
		reg = <0x0 0xd5100000 0x0 0x500000>;
		width = <3200>;
		height = <400>;"""
new = """		/* Keep this small: enlarging it changes the pre-relocation memory
		 * carving and stops the F->R hand-off (diag3 hang). The console is not
		 * used on this board - lib/initcall.c draws its own text. */
		reg = <0x0 0xd5100000 0x0 0x100000>;
		width = <640>;
		height = <400>;"""
assert s.count(old) == 1, ("dts", s.count(old))
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.replace(old, new))
print("dts: framebuffer geometry reverted to 640x400 / 1 MiB")

# --- 2) lib/initcall.c: fixed-row hex helper -------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "tb_screen_fixed_hex" not in s

helper = '''
/*
 * Same as tb_screen_log_hex(), but always at the same row so that repeated
 * calls overwrite each other - used to name the initcall we are about to run.
 */
void tb_screen_fixed_hex(int y, ulong v, int scale)
{
	char txt[9];
	char *p = txt;

	tb_put_hex(&p, v, 8);
	*p = 0;
	tb_fb_clear_at(TB_LOG_X, y, 8 * 8 * scale + 8, 16 * scale + 8,
		       TB_LOG_STRIDE, 1);
	tb_screen_text(TB_LOG_X, y, txt, scale);
}
'''
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.rstrip("\n") + "\n" + helper)
print("initcall.c: tb_screen_fixed_hex added")

# --- 3) board_f.c: BLUE sentinel after the yellow block --------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """			for (c = 0; c < 400; c++)
				line[c] = 0xFFFFFF00;
		}
	}
"""
new = """			for (c = 0; c < 400; c++)
				line[c] = 0xFFFFFF00;
		}
	}

	/* TB710FU: BLUE = board_init_f is about to return to crt0, which then
	 * relocates U-Boot and calls board_init_r(). */
	{
		unsigned *fb = (unsigned *)0xD5100000UL;
		int r, c;

		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(550 + r) * 3200 + 700;

			for (c = 0; c < 400; c++)
				line[c] = 0xFF0000FF;
		}
	}
"""
assert s.count(old) == 1, ("board_f yellow anchor", s.count(old))
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.replace(old, new))
print("board_f.c: blue sentinel added")

# --- 4) board_r.c: RED sentinel + per-index logging -----------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

proto = "void tb_screen_fixed_hex(int y, ulong v, int scale);"
if proto not in s:
    anchor = "void tb_screen_log_reset(void);"
    assert anchor in s
    s = s.replace(anchor, anchor + "\n" + proto, 1)

old = """	{
		int i;

		for (i = 0; i < 14; i++) {
			init_fnc_t fn = init_sequence_r[i];

			if (!fn || ((ulong)fn & INITCALL_IS_EVENT))
				continue;
			if (fn())
				break;
		}
	}

	tb_screen_log_reset();
	tb_screen_log("TB710FU DIAG3", 5);"""
new = """	/* TB710FU: RED = board_init_r was reached, i.e. relocate_code and the
	 * crt0 hand-off both worked. This is the first statement on purpose. */
	{
		unsigned *fb = (unsigned *)0xD5100000UL;
		int r, c;

		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(800 + r) * 3200 + 700;

			for (c = 0; c < 400; c++)
				line[c] = 0xFFFF0000;
		}
	}

	{
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

	tb_screen_log_reset();
	tb_screen_log("TB710FU DIAG4", 5);"""
assert s.count(old) == 1, ("board_r loop anchor", s.count(old))
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.replace(old, new))
print("board_r.c: red sentinel + per-index logging installed")
