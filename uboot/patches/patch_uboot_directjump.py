#!/usr/bin/env python3
# TB710FU: after the F sequence, jump straight to the mainline kernel that
# is appended in this same boot.img -- skipping U-Boot's relocation and the
# whole R sequence (both of which hang on this board).
#   kernel Image @ 0xA8000000, our DTB @ 0xAAA12000
f = '/home/meteor/u-boot-13r/common/board_f.c'
s = open(f).read()

anchor = '\t/* TB710FU: YELLOW block = F sequence returned (hang is after this) */'
assert anchor in s, 'yellow beacon anchor not found'

start = s.index(anchor)
end = s.index('\t}\n', s.index('line[c] = 0xFFFFFF00;', start)) + len('\t}\n')

jump_block = '''	/* TB710FU: YELLOW = F sequence returned (hang is after this) */
	{
		unsigned *fb = (unsigned *)0xD5100000UL;
		int r, c;

		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(300 + r) * 3200 + 700;

			for (c = 0; c < 400; c++)
				line[c] = 0xFFFFFF00;
		}
	}

	/* TB710FU: hand off directly to the appended mainline kernel; this
	 * skips U-Boot's relocation and the whole R sequence (both hang).
	 * arm64 Image entry takes the DTB physical address in x0. */
	{
		typedef void (*kernel_entry_t)(void *dtb, void *r1, void *r2,
					       void *r3);
		unsigned *fb = (unsigned *)0xD5100000UL;
		kernel_entry_t k = (kernel_entry_t)0xA8000000UL;
		int r, c;

		/* CYAN = about to jump into the kernel */
		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(600 + r) * 3200 + 700;

			for (c = 0; c < 400; c++)
				line[c] = 0xFF00FFFF;
		}

		k((void *)0xAAA12000UL, NULL, NULL, NULL);
		for (;;)
			;
	}
'''
s = s[:start] + jump_block + s[end:]
open(f, 'w').write(s)
print('direct kernel handoff installed (kernel 0xA8000000, dtb 0xAAA12000)')