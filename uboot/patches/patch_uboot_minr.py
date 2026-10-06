#!/usr/bin/env python3
# TB710FU: U-Boot is only a thin loader for us -- run the essential early
# R-sequence steps and jump straight to the main loop (bootcmd -> booti).
# The DM/stdio device-probe block hangs with the stubbed clocks.
f = '/home/meteor/u-boot-13r/common/board_r.c'
s = open(f).read()

old = '''	if (initcall_run_list(init_sequence_r))
		hang();'''
new = '''	/* TB710FU: minimal R sequence. The device-probe/stdio block hangs
	 * with the stubbed clocks; we only need reloc/malloc/DM/board_init
	 * before jumping to the loader (run_main_loop -> bootcmd -> booti). */
	{
		int i;

		for (i = 0; i < 12; i++) {
			init_fnc_t fn = init_sequence_r[i];

			if (!fn || ((ulong)fn & INITCALL_IS_EVENT))
				continue;
			if (fn())
				break;
		}
	}
	run_main_loop();
	hang();'''
assert old in s, 'board_r initcall anchor not found'
s = s.replace(old, new, 1)
open(f, 'w').write(s)
print('minimal R sequence installed (jump to main loop)')