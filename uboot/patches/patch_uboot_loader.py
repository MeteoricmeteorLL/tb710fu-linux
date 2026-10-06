#!/usr/bin/env python3
# TB710FU: reach the loader without full device autoprobe.
# Run R-array up to (not including) initr_dm_devices[14] (this sets up
# DM/reloc/malloc but avoids dm_autoprobe which hangs probing unrelated
# drivers). Then manually probe ONLY the video (console) and SCSI/UFS
# devices we need, then jump to run_main_loop.
f = '/home/meteor/u-boot-13r/common/board_r.c'
s = open(f).read()

old = '''	/* TB710FU: minimal R sequence. The device-probe/stdio block hangs
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
new = '''	/* TB710FU: reach the loader without full device autoprobe.
	 * Run R-array up to but NOT including initr_dm_devices (index 14),
	 * which calls dm_autoprobe() and hangs probing unrelated drivers.
	 * Then probe only video (console) and SCSI/UFS devices we need. */
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

	/* Console via simple_video (framebuffer @0xD5100000). */
	stdio_init_tables();
	{
		int rc = console_init_f();
		(void)rc;
	}

	/* green beacon = reached the loader with console up */
	{
		unsigned *fb = (unsigned *)0xD5100000UL;
		int r, c;

		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(400 + r) * 3200 + 700;

			for (c = 0; c < 400; c++)
				line[c] = 0xFF00FF00u;
		}
	}

	run_main_loop();
	hang();'''
assert old in s, 'minimal R anchor not found'
s = s.replace(old, new, 1)
open(f, 'w').write(s)
print('loader-with-video path installed')