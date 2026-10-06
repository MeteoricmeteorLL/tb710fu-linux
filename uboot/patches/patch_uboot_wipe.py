#!/usr/bin/env python3
# TB710FU: clear the whole framebuffer at boot start so any visible content
# is provably from THIS boot (the panel keeps old frames across resets).
f = '/home/meteor/u-boot-13r/common/board_f.c'
s = open(f).read()
old = '''static void tb_banner_early(void)
{
	unsigned *fb = (unsigned *)0xD5100000UL;
	int row, col;

	for (row = 0; row < 240; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 600; col++)
			line[col] = 0xFF00FF00; /* GREEN = early banner */
	}'''
new = '''static void tb_banner_early(void)
{
	unsigned *fb = (unsigned *)0xD5100000UL;
	int row, col;

	/* 1) wipe the whole panel so nothing from a previous boot remains */
	for (row = 0; row < 2000; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 3200; col++)
			line[col] = 0xFF000000;
	}

	/* 2) green banner = "this boot, board_init_f running" */
	for (row = 0; row < 240; row++) {
		unsigned *line = fb + (ulong)row * 3200;

		for (col = 0; col < 600; col++)
			line[col] = 0xFF00FF00;
	}'''
assert old in s, 'banner anchor not found'
s = s.replace(old, new, 1)
open(f, 'w').write(s)
print('screen wipe installed before banner')