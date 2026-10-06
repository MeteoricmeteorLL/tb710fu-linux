#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #2.

1) board.c: force the internal FDT so our simple-framebuffer node exists
   (memory is still parsed from the external ABL DT, so RAM layout is unchanged).
2) lib/initcall.c: export tb_screen_hexline() - draw an 8-digit hex word on the
   ABL splash framebuffer using the 8x16 font already in that file.
3) board_r.c: probe VIDEO and UFS (not SCSI, whose devices only exist after a
   scan), print every return code as text, then register stdio + console and
   run scsi_scan().
No UART: the screen is the only output channel, so RC values are printed, not
colour-coded.
"""
import io
import re

U = "/home/meteor/u-boot-13r/"

# ---------------------------------------------------------------- board.c
p = U + "arch/arm/mach-snapdragon/board.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = '''	if (external_valid) {
		debug("Using external ABL FDT\\n");
		*fdtp = external_fdt;
		ret = 0;
	} else {
		debug("Using built in FDT\\n");
		ret = -EEXIST;
	}'''
new = '''	if (internal_valid) {
		/* TB710FU: the embedded DT carries the simple-framebuffer node that
		 * gives U-Boot a vidconsole on the ABL splash framebuffer. Memory was
		 * already parsed from the external ABL DT above, so RAM layout is
		 * unchanged. */
		debug("TB710FU: forcing internal FDT for the video console\\n");
		*fdtp = internal_fdt;
		ret = 0;
	} else if (external_valid) {
		debug("Using external ABL FDT\\n");
		*fdtp = external_fdt;
		ret = 0;
	} else {
		ret = -EEXIST;
	}'''
assert s.count(old) == 1, ("board.c anchor", s.count(old))
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.replace(old, new))
print("board.c: internal FDT forced")

# ------------------------------------------------------------ lib/initcall.c
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "tb_screen_hexline" not in s

helper = '''
/*
 * TB710FU: draw an 8-digit hex word at (8,y) on the splash framebuffer.
 * The console needs a probed video device, so the first thing this board can
 * print is written directly to the ABL framebuffer with the 8x16 font above.
 */
void tb_screen_hexline(int y, ulong v)
{
	char txt[9];
	char *p = txt;
	int k;

	tb_put_hex(&p, v, 8);
	*p = 0;

	tb_fb_clear_at(8, y, 8 * 26 + 4, 18, 3200, 3);
	for (k = 0; k < 8; k++)
		tb_fb_char_at(8 + k * 26, y, txt[k], 3200, 3);
}
'''
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.rstrip("\n") + "\n" + helper)
print("initcall.c: tb_screen_hexline added")

# ------------------------------------------------------------- board_r.c
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

if "#include <scsi.h>" not in s:
    anchor = "#include <env.h>"
    if anchor not in s:
        anchor = "#include <common.h>"
    assert anchor in s
    s = s.replace(anchor, anchor + "\n#include <scsi.h>", 1)

if "void tb_screen_hexline(int y, ulong v);" not in s:
    anchor = "#include <scsi.h>"
    s = s.replace(anchor, anchor + "\n\n/* lib/initcall.c */\nvoid tb_screen_hexline(int y, ulong v);", 1)

start = s.index("\t/* TB710FU: reach the loader without full device autoprobe.")
end = s.index("\trun_main_loop();", start)

new_block = '''\t/* TB710FU: reach the loader without full device autoprobe.
	 * Run R-array up to but NOT including initr_dm_devices (index 14), which
	 * calls dm_autoprobe() and hangs probing unrelated drivers. Then bring up
	 * only what we need: the video console and the UFS host controller.
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

	/* There is no UART on this board, so results are printed onto the ABL
	 * splash framebuffer as 8-digit hex words at a fixed row each:
	 *   row 560 = uclass_first_device_err(UCLASS_VIDEO)   0 => console possible
	 *   row 620 = uclass_first_device_err(UCLASS_UFS)     0 => host controller ok
	 *   row 680 = stdio_add_devices()
	 *   row 740 = console_init_r()
	 *   row 800 = scsi_scan(true)
	 *   row 860 = number of UCLASS_SCSI devices
	 *   row 920 = gd->flags
	 * errno values to expect: ffffffed = -ENODEV, fffffffb = -ENOENT,
	 * ffffffea = -EINVAL, ffffffef = -EIO, fffffdfb = -EPROBE_DEFER.
	 */
	{
		struct udevice *dv = NULL, *uv = NULL;
		int video_rc, ufs_rc;
		unsigned *fb = (unsigned *)0xD5100000UL;
		int r, c;

		video_rc = uclass_first_device_err(UCLASS_VIDEO, &dv);
		tb_screen_hexline(560, (ulong)(unsigned int)video_rc);

		/* Colour block as a coarse cross-check of the video probe:
		 * green = probed, yellow = error, red = EPROBE_DEFER. */
		{
			unsigned col = video_rc == 0 ? 0xFF00FF00u :
				(video_rc == -EPROBE_DEFER ? 0xFFFF0000u : 0xFFFFFF00u);

			for (r = 0; r < 140; r++) {
				unsigned *line = fb + (ulong)(400 + r) * 3200 + 700;

				for (c = 0; c < 400; c++)
					line[c] = col;
			}
		}

		ufs_rc = uclass_first_device_err(UCLASS_UFS, &uv);
		tb_screen_hexline(620, (ulong)(unsigned int)ufs_rc);
		(void)dv;
		(void)uv;
	}

	/* green beacon = reached the loader, probes done */
	{
		unsigned *fb = (unsigned *)0xD5100000UL;
		int r, c;

		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(400 + r) * 3200 + 1400;

			for (c = 0; c < 400; c++)
				line[c] = 0xFF00FF00u;
		}
	}

	/* Register the stdio devices (this is what puts vidconsole in the device
	 * list) and fully initialise the console. CONFIG_SYS_CONSOLE_IS_IN_ENV=y,
	 * so console_init_r() takes the console from the environment: point it at
	 * vidconsole, which is the only channel this board has. */
	{
		int rc;

		env_set("stdin", "vidconsole");
		env_set("stdout", "vidconsole");
		env_set("stderr", "vidconsole");

		stdio_init_tables();

		rc = console_init_f();
		(void)rc;

		rc = stdio_add_devices();
		tb_screen_hexline(680, (ulong)(unsigned int)rc);

		rc = console_init_r();
		tb_screen_hexline(740, (ulong)(unsigned int)rc);
	}

	printf("TB710FU: loader reached, flags=%08x\\n", gd->flags);

	/* UFS/SCSI: scan the bus the way 'scsi scan' does, then count what turned
	 * up in the SCSI uclass (SCSI devices are created by the scan, they are
	 * never bound from the DT). */
	{
		struct udevice *sv;
		int rc, n = 0;

		rc = scsi_scan(true);
		tb_screen_hexline(800, (ulong)(unsigned int)rc);

		while (n < 16 && uclass_find_device(UCLASS_SCSI, n, &sv) == 0)
			n++;
		tb_screen_hexline(860, (ulong)n);
	}

	tb_screen_hexline(920, (ulong)(unsigned int)gd->flags);

'''
s = s[:start] + new_block + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: diagnostic block installed")
