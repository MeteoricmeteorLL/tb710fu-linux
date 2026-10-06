#!/usr/bin/env python3
# Reset U-Boot TB710FU hacks to a clean, verifiable state:
#  - drop the tb_rebuild_* (0xD6A/B00000) path that hangs early boot
#  - use plain initcall_run_list again
#  - add a WHITE "main loop reached" beacon + build tag for unambiguous
#    on-screen evidence (the framebuffer persists across resets)
UB = '/home/meteor/u-boot-13r'

# ---- board_f.c: plain F sequence ----
f = UB + '/common/board_f.c'
s = open(f).read()
old = '''	/* TB710FU: ABL places its DTB over parts of our .data (the R array
	 * region), so REBUILD the F sequence from hard-coded link offsets
	 * instead of trusting the clobbered array, into splash-pool RAM. */
	{
		tb_rebuild_f((init_fnc_t *)0xD6A00000UL);
		if (initcall_run_list((init_fnc_t *)0xD6A00000UL))
			hang();
	}
	if (0)
		initcall_run_list(init_sequence_f);
	if (0)
		hang();'''
new = '''	if (initcall_run_list(init_sequence_f))
		hang();'''
assert old in s, 'board_f anchor not found'
s = s.replace(old, new, 1)
s = s.replace('#include "initseq_rebuild.inc"\n', '')
open(f, 'w').write(s)

# ---- board_r.c: plain R sequence + main-loop beacon ----
f = UB + '/common/board_r.c'
s = open(f).read()
old = '''	/* TB710FU: the .data copy the relocation produced was built from a
	 * DTB-clobbered source; REBUILD the R sequence from hard-coded link
	 * offsets + reloc_off into splash-pool RAM. */
	{
		tb_rebuild_r((init_fnc_t *)0xD6B00000UL, gd->reloc_off);
	}
	if (initcall_run_list((init_fnc_t *)0xD6B00000UL))
		hang();'''
new = '''	if (initcall_run_list(init_sequence_r))
		hang();'''
assert old in s, 'board_r anchor not found'
s = s.replace(old, new, 1)
s = s.replace('#include "initseq_rebuild.inc"\n', '')

# beacon + tag drawn right before the main loop
beacon = '''
/* TB710FU: unmistakable on-screen evidence that init finished. */
static void tb_beacon(void)
{
	unsigned *fb = (unsigned *)0xD5100000UL;
	int row, col;

	/* tag block: 200x200 at (1600,100) filled 0x00FF00FF (magenta) */
	for (row = 0; row < 200; row++) {
		unsigned *line = fb + (ulong)(100 + row) * 3200 + 1600;

		for (col = 0; col < 200; col++)
			line[col] = 0xFFFF00FF;
	}
	/* main-loop beacon: 600x200 at (1900,100) solid WHITE */
	for (row = 0; row < 200; row++) {
		unsigned *line = fb + (ulong)(100 + row) * 3200 + 1900;

		for (col = 0; col < 600; col++)
			line[col] = 0xFFFFFFFF;
	}
}

'''
anchor = 'static int run_main_loop(void)'
assert anchor in s, 'run_main_loop anchor not found'
s = s.replace(anchor, beacon + anchor, 1)
s = s.replace('static int run_main_loop(void)\n{', 'static int run_main_loop(void)\n{\n\ttb_beacon();', 1)
open(f, 'w').write(s)
print('reset to plain initcall lists + beacon installed')