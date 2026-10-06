#!/usr/bin/env python3
"""TB710FU U-Boot build #22 - don't autoprobe every driver.

Build #21 logged each R-sequence entry's function address, and the last one was
0x35898 = initr_dm. Reading it explains why:

    static int initr_dm(void)
    {
        ...
        ret = dm_init_and_scan(false);   <- binds devices from the DT, harmless
        ...
        return dm_autoprobe();           <- probes EVERY driver, and hangs
    }

So initr_dm's tail is the hang, which is the same "probing unrelated drivers
hangs" the previous session hit - it just attributed it to initr_dm_devices.

What we actually need is dm_init_and_scan(): it binds devices from the device
tree without probing them. Then our explicit uclass_first_device_err(UCLASS_UFS)
probes exactly the controller we want, and nothing else. So:

  * skip initr_dm, and do its essential prologue ourselves (oftree_reset,
    dm_root/timer reset) plus dm_init_and_scan(false), logging the result;
  * probe the timer device explicitly - U-Boot's delays and timeouts need it and
    it used to come from the autoprobe we are removing;
  * then UFS and the SCSI scan as before.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# 1) skip initr_dm alongside initr_caches
old = """			if (init_sequence_r[i] == (init_fnc_t)initr_caches)
				continue;"""
new = """			if (init_sequence_r[i] == (init_fnc_t)initr_caches)
				continue;
			/* TB710FU: initr_dm ends with dm_autoprobe(), which probes
			 * every driver and hangs on this board. Only the scan is
			 * wanted, and it is done explicitly below. */
			if (init_sequence_r[i] == (init_fnc_t)initr_dm)
				continue;"""
assert s.count(old) == 1, ("skip caches", s.count(old))
s = s.replace(old, new, 1)

# 2) after the sequence, do the bind-only DM init and probe the timer
old = """	tb_screen_log("PROBE UFS", 3);"""
new = """	/* TB710FU: the DM scan without the autoprobe that initr_dm would run.
	 * This binds devices from the device tree; probing is left to the explicit
	 * calls below, so only the UFS controller is touched. The prologue mirrors
	 * initr_dm so the driver model starts from a clean state. */
	tb_screen_log("DM INIT AND SCAN", 3);
	{
		int rc;

		oftree_reset();
		gd->dm_root = NULL;
#ifdef CONFIG_TIMER
		gd->timer = NULL;
#endif
		rc = dm_init_and_scan(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		/* The autoprobe we no longer run used to provide the timer; U-Boot's
		 * delays and timeouts need one, so probe it explicitly. */
		{
			struct udevice *tv = NULL;

			rc = uclass_first_device_err(UCLASS_TIMER, &tv);
			tb_screen_log(rc ? "TIMER FAIL" : "TIMER OK", 3);
			tb_screen_log_hex((ulong)(unsigned int)rc, 3);
		}
	}

	tb_screen_log("PROBE UFS", 3);"""
assert s.count(old) == 1, ("probe head", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: initr_dm skipped, bind-only scan + timer probe added")
