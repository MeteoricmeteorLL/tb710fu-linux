#!/usr/bin/env python3
# Make U-Boot render the previous session's initcall markers on screen.
f = '/home/meteor/u-boot-13r/common/board_f.c'
s = open(f).read()

# 1) include the 8x16 font data
old_inc = '#include <asm/global_data.h>'
assert old_inc in s, 'include anchor not found'
s = s.replace(old_inc, old_inc + '\n#include <video_font_8x16.h>', 1)

# 2) extend the early banner with marker rendering
old = '''static void tb_banner_early(void)
{
	unsigned *fb = (unsigned *)0xD5100000UL;
	int row, col;

	for (row = 0; row < 240; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 600; col++)
			line[col] = 0xFF00FF00; /* GREEN = early banner */
	}
}'''
new = '''static void tb_draw_char16(int x, int y, unsigned char c, unsigned color)
{
	const unsigned char *g;
	int row, col;
	unsigned *fb = (unsigned *)0xD5100000UL;

	g = &video_fontdata_8x16[(int)c * 16];
	for (row = 0; row < 16; row++) {
		unsigned *line = fb + (ulong)(y + row) * 3200 + x;
		unsigned char bits = g[row];

		for (col = 0; col < 8; col++)
			line[col] = (bits & (0x80 >> col)) ? color : 0xFF000000;
	}
}

static void tb_draw_str(int x, int y, const char *s, unsigned color)
{
	while (*s) {
		tb_draw_char16(x, y, *s++, color);
		x += 9;
	}
}

static void tb_banner_early(void)
{
	unsigned *fb = (unsigned *)0xD5100000UL;
	int row, col;

	for (row = 0; row < 240; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 600; col++)
			line[col] = 0xFF00FF00; /* GREEN = early banner */
	}

	/*
	 * TB710FU: render the PREVIOUS session's initcall markers
	 * ("<idx>:<func>" lines in no-map RAM at 0x9b09c000). They survive
	 * the warm reboot chain, and drawing them here happens before
	 * this session overwrites them.
	 */
	{
		const char *p = (const char *)0x9b09c000UL;
		char linebuf[16];
		int i, n = 0, line = 0;

		for (i = 0; i < 1100 && n < 900; i++) {
			char c = p[i];

			linebuf[n++] = c;
			if (c == '\\n' || n == 14) {
				int k;

				linebuf[n] = 0;
				if (n > 1)
					tb_draw_str(620, 8 + line * 16,
						    linebuf, 0xFFFFFFFF);
				line++;
				if (line >= 118)
					break;
				n = 0;
			}
		}
	}
}'''
assert old in s, 'banner anchor not found'
s = s.replace(old, new, 1)
open(f, 'w').write(s)
print('marker renderer installed in board_init_f')