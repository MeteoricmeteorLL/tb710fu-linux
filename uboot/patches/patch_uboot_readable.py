#!/usr/bin/env python3
# Make U-Boot progress readable: drop the screen-filling cyan array dump,
# draw the step code big below the banner, clearing first.
UB = '/home/meteor/u-boot-13r'

# ---- board_r.c: remove the cyan dump call ----
f = UB + '/common/board_r.c'
s = open(f).read()
import re
before = s
s = re.sub(r'\ttbr_dump_array\(init_sequence_r\);\n', '', s)
if s == before:
    # maybe called differently
    s = re.sub(r'[ \t]*tbr_dump_array\([^;]*\);\n', '', s)
assert 'tbr_dump_array(init_sequence_r);' not in s, 'dump call still present'
open(f, 'w').write(s)
print('cyan array dump call removed')

# ---- initcall.c: bigger digits below the banner ----
f = UB + '/lib/initcall.c'
s = open(f).read()
old = '''		for (si = 0; si < 2; si++) {
			int xs = 8 + si * 190;

			tb_fb_clear_at(xs, 8, 10, 16, tb_strides[si], 2);
			for (k = 0; k < 9; k++)
				tb_fb_char_at(xs + k * 18, 8, txt[k],
					      tb_strides[si], 2);
		}'''
new = '''		/* big, cleared-first code below the banner area (y=0..240) */
		(void)si;
		tb_fb_clear_at(8, 300, 9 * 26 + 4, 16 * 3, 3200, 3);
		for (k = 0; k < 9; k++)
			tb_fb_char_at(8 + k * 26, 300, txt[k], 3200, 3);'''
assert old in s, 'digit block anchor not found'
s = s.replace(old, new, 1)
# tick bar on row 0 conflicts with the banner; move to row 2 of the area below banner
s = s.replace('''	{
		unsigned *line = (unsigned *)TB_FB_BASE;
		unsigned tick;

		for (tick = 0; tick < 8; tick++)
			line[(ulong)idx * 8 + tick] = 0xFFFF0000; /* RED: build marker */
	}''', '''	{
		unsigned *line = (unsigned *)TB_FB_BASE +
				 (ulong)400 * 3200;
		unsigned tick;

		for (tick = 0; tick < 8; tick++)
			line[(ulong)idx * 8 + tick] = 0xFFFF0000;
	}''')
open(f, 'w').write(s)
print('digits -> big, y=300, cleared first')
