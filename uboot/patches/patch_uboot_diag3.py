#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #3.

Why: diag #2 proved a vidconsole existed (text appeared) but every line was
sheared, because simplefb derives its row pitch from the DTS "width" (640) while
the panel scans 3200 pixels per row. And the numeric log rows were ambiguous.

Changes:
1) DTS: framebuffer width=3200 (defines the row pitch), height capped to 400
   rows so the console cannot walk past the splash region; reg size 5 MiB.
2) lib/initcall.c: bring in U-Boot's own CP437 8x16 font and add a big-text log
   (tb_screen_log / tb_screen_log_hex) that draws directly into the splash
   framebuffer at any integer scale, independent of the DM console.
3) board_r.c: report each bring-up step as readable words plus its return code,
   then ask the vidconsole for the 16x32 font.
"""
import io

U = "/home/meteor/u-boot-13r/"

# ------------------------------------------------------------------ DTS
p = U + "dts/upstream/src/arm64/qcom/sm8650-lenovo-tb710fu.dts"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """	framebuffer@d5100000 {
		compatible = "simple-framebuffer";
		reg = <0x0 0xd5100000 0x0 0x100000>;
		width = <640>;
		height = <400>;
		stride = <2560>;
		format = "a8r8g8b8";
	};"""
new = """	framebuffer@d5100000 {
		compatible = "simple-framebuffer";
		/* simplefb derives the row pitch from "width", so it has to match the
		 * panel (3200) or every console line shears across the screen. "height"
		 * only caps how many rows the console may use, and "reg" has to cover
		 * width * height * 4 bytes. */
		reg = <0x0 0xd5100000 0x0 0x500000>;
		width = <3200>;
		height = <400>;
		format = "a8r8g8b8";
	};"""
assert s.count(old) == 1, ("dts anchor", s.count(old))
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.replace(old, new))
print("dts: framebuffer geometry fixed (3200 wide, 400 rows)")

# ---------------------------------------------------------- lib/initcall.c
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "tb_screen_log(" not in s

lines = s.split("\n")
last_inc = max(i for i, l in enumerate(lines[:60]) if l.startswith("#include"))
lines.insert(last_inc + 1,
             "#include <video_font_data.h>\n#include <video_font_8x16.h>")
s = "\n".join(lines)

helper = '''
/* ---------------------------------------------------------------------------
 * TB710FU: on-screen text log.
 *
 * There is no UART on this board, so the only output channel is the framebuffer
 * ABL left behind at 0xD5100000, which the display pipeline keeps scanning out
 * even after the hand-off to U-Boot. U-Boot's own console is optional and its
 * default glyphs are 8x16 pixels, which is unreadable on a 3200x2000 panel, so
 * messages are drawn here directly at an integer scale from U-Boot's CP437
 * font. A line is short enough to read off a photo of the screen.
 * ------------------------------------------------------------------------- */
#define TB_LOG_X		8
#define TB_LOG_TOP		420
#define TB_LOG_STRIDE		3200

static int tb_log_y = TB_LOG_TOP;

void tb_screen_log_reset(void)
{
	tb_log_y = TB_LOG_TOP;
}

void tb_screen_text(int x, int y, const char *s, int scale)
{
	unsigned *fb = (unsigned *)TB_FB_BASE;
	int i;

	for (i = 0; s[i]; i++) {
		const unsigned char *g =
			&video_fontdata_8x16[(unsigned char)s[i] * 16];
		int row, col, dy, dx;

		for (row = 0; row < 16; row++) {
			for (col = 0; col < 8; col++) {
				unsigned v = (g[row] & (0x80 >> col)) ?
					TB_COLOR_WHITE : TB_COLOR_BLACK;
				unsigned *line = fb +
					(ulong)(y + row * scale) * TB_LOG_STRIDE +
					x + i * 8 * scale + col * scale;

				for (dy = 0; dy < scale; dy++)
					for (dx = 0; dx < scale; dx++)
						line[(ulong)dy * TB_LOG_STRIDE + dx] =
							v;
			}
		}
	}
}

void tb_screen_log(const char *s, int scale)
{
	tb_fb_clear_at(TB_LOG_X, tb_log_y, TB_LOG_STRIDE - 32,
		       16 * scale + 8, TB_LOG_STRIDE, 1);
	tb_screen_text(TB_LOG_X, tb_log_y, s, scale);
	tb_log_y += 16 * scale + 20;
}

void tb_screen_log_hex(ulong v, int scale)
{
	char txt[9];
	char *p = txt;

	tb_put_hex(&p, v, 8);
	*p = 0;
	tb_screen_log(txt, scale);
}
'''
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.rstrip("\n") + "\n" + helper)
print("initcall.c: big-text log added")

# ------------------------------------------------------------- board_r.c
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

for inc, after in (("#include <video_console.h>", "#include <scsi.h>"),):
    if inc not in s:
        assert after in s
        s = s.replace(after, after + "\n" + inc, 1)

for proto in ("void tb_screen_log(const char *s, int scale);",
              "void tb_screen_log_hex(ulong v, int scale);",
              "void tb_screen_log_reset(void);"):
    if proto not in s:
        anchor = "void tb_screen_hexline(int y, ulong v);"
        assert anchor in s
        s = s.replace(anchor, anchor + "\n" + proto, 1)

start = s.index("\t/* TB710FU: reach the loader without full device autoprobe.")
end = s.index("\trun_main_loop();", start)

new_block = '''\t/* TB710FU: reach the loader without full device autoprobe.
	 * Run R-array up to but NOT including initr_dm_devices (index 14), which
	 * calls dm_autoprobe() and hangs probing unrelated drivers. Everything
	 * after this point is brought up explicitly, one step at a time, and
	 * reported on screen as text plus the return code in hex.
	 */
	{
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
	tb_screen_log("TB710FU DIAG3", 5);

	{
		struct udevice *dv = NULL;
		int rc = uclass_first_device_err(UCLASS_VIDEO, &dv);

		tb_screen_log(rc ? "VIDEO FAIL" : "VIDEO OK", 5);
		tb_screen_log_hex((ulong)(unsigned int)rc, 4);
		if (dv)
			tb_screen_log(dv->name, 3);
	}

	{
		struct udevice *uv = NULL;
		int rc = uclass_first_device_err(UCLASS_UFS, &uv);

		tb_screen_log(rc ? "UFS FAIL" : "UFS OK", 5);
		tb_screen_log_hex((ulong)(unsigned int)rc, 4);
		if (uv)
			tb_screen_log(uv->name, 3);
	}

	{
		int rc;

		/* CONFIG_SYS_CONSOLE_IS_IN_ENV=y: console_init_r() takes the console
		 * from the environment, and vidconsole is the only channel here. */
		env_set("stdin", "vidconsole");
		env_set("stdout", "vidconsole");
		env_set("stderr", "vidconsole");

		stdio_init_tables();
		console_init_f();

		rc = stdio_add_devices();
		tb_screen_log(rc ? "STDIO FAIL" : "STDIO OK", 5);
		tb_screen_log_hex((ulong)(unsigned int)rc, 4);

		rc = console_init_r();
		tb_screen_log(rc ? "CONSOLE FAIL" : "CONSOLE OK", 5);
		tb_screen_log_hex((ulong)(unsigned int)rc, 4);
	}

	printf("TB710FU: loader reached, flags=%08x\\n", gd->flags);

	{
		struct udevice *cons = NULL;
		int rc = uclass_first_device(UCLASS_VIDEO_CONSOLE, &cons);

		if (!rc && cons) {
			int frc = vidconsole_select_font(cons, "16x32", 0);

			tb_screen_log(frc ? "FONT FAIL" : "FONT 16X32", 5);
			tb_screen_log_hex((ulong)(unsigned int)frc, 4);
		}
	}

	{
		struct udevice *sv;
		int rc, n = 0;

		rc = scsi_scan(true);
		tb_screen_log(rc ? "SCSI SCAN FAIL" : "SCSI SCAN OK", 5);
		tb_screen_log_hex((ulong)(unsigned int)rc, 4);

		for (uclass_first_device(UCLASS_SCSI, &sv); sv;
		     uclass_next_device(&sv))
			n++;
		tb_screen_log("SCSI COUNT", 5);
		tb_screen_log_hex((ulong)n, 4);
	}

	tb_screen_log("GD FLAGS", 5);
	tb_screen_log_hex((ulong)(unsigned int)gd->flags, 4);

'''
s = s[:start] + new_block + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: text-log block installed")
