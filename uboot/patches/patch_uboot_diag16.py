#!/usr/bin/env python3
"""TB710FU U-Boot build #16 - drop video/console bring-up, go for storage.

Build #15 finally ran the whole way: the log printed "R ENTRIES BEFORE DM DEV
0000000e" (14 entries, matching the truncation) with return code 0, the marker
bars for the whole relocation path appeared and the red "board_init_r entered"
sentinel is on screen. The relocation saga is over, and the R sequence really
does run now - the initcall_run_list fix is confirmed.

The new blocker is right after it: nothing is logged past the R sequence, and
the first thing after it is the explicit UCLASS_VIDEO probe. That probe is not
needed at all - lib/initcall.c draws the log straight into the splash
framebuffer, so vidconsole buys nothing - while simplefb's post-probe path
(framebuffer clear, vidconsole bind, splash) is a prime suspect for a hang.

So remove the video probe, stdio/console init and the font selection, keep the
storage path, and log a line before each step so a hang names itself.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

start = s.index("	{\n		struct udevice *dv = NULL;\n		int rc = uclass_first_device_err(UCLASS_VIDEO, &dv);")
end = s.index("	run_main_loop();", start)

new = '''	/* TB710FU: the video device is deliberately not probed. Its driver's
	 * post-probe path never returns on this board, and it is not needed:
	 * lib/initcall.c draws the log directly into the splash framebuffer that
	 * the display pipeline is already scanning out. What this bring-up
	 * actually needs is storage, so that is what gets probed. Each step logs
	 * a line before it runs, so a hang names itself on the next photo. */
	tb_screen_log("PROBE UFS", 3);

	{
		struct udevice *uv = NULL;
		int rc = uclass_first_device_err(UCLASS_UFS, &uv);

		tb_screen_log(rc ? "UFS FAIL" : "UFS OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);
		if (uv)
			tb_screen_log(uv->name, 3);
	}

	tb_screen_log("SCSI SCAN", 3);

	{
		struct udevice *sv;
		int rc, n = 0;

		rc = scsi_scan(true);
		tb_screen_log(rc ? "SCSI FAIL" : "SCSI OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		for (uclass_first_device(UCLASS_SCSI, &sv); sv;
		     uclass_next_device(&sv))
			n++;
		tb_screen_log("SCSI COUNT", 3);
		tb_screen_log_hex((ulong)n, 3);
	}

	tb_screen_log("GD FLAGS", 3);
	tb_screen_log_hex((ulong)(unsigned int)gd->flags, 3);

'''
s = s[:start] + new + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: video/console bring-up removed, storage probe logged")
