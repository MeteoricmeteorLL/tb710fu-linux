#!/usr/bin/env python3
"""TB710FU U-Boot build #23 - turn off CONFIG_OF_LIVE, split the DM steps.

Build #22 reached "R SEQ OK" (return code 0) and then stopped on my own
dm_init_and_scan(false) call. So dm_autoprobe() was not the culprit after all -
dm_init_and_scan itself hangs, and both halves of it take the CONFIG_OF_LIVE
"live tree" path: dm_init(OF_LIVE) sets the tree up and dm_scan() walks it when
binding. initr_of_live built that tree from the flat blob and returned 0, but
walking it is the remaining suspect.

Changes:
  * CONFIG_OF_LIVE off, so the driver model uses the flat device tree - the
    classic U-Boot mode, and our DTB is intact at gd->fdt_blob;
  * call dm_init(false) and dm_scan(false) separately with a log line before and
    the return code after each, so if it still hangs the log names the half.
"""
import io
import subprocess

U = "/home/meteor/u-boot-13r/"

# --- 1) config: OF_LIVE off ------------------------------------------------
subprocess.check_call([U + "scripts/config", "--file", U + ".config",
                       "-d", "OF_LIVE"], cwd=U)
print("config: CONFIG_OF_LIVE disabled")

# --- 2) board_r.c: split dm_init / dm_scan ---------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

if "#include <dm/root.h>" not in s:
    anchor = "#include <scsi.h>"
    assert anchor in s
    s = s.replace(anchor, anchor + "\n#include <dm/root.h>", 1)

old = """		oftree_reset();
		gd->dm_root = NULL;
#ifdef CONFIG_TIMER
		gd->timer = NULL;
#endif
		rc = dm_init_and_scan(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);
"""
new = """		oftree_reset();
		gd->dm_root = NULL;
#ifdef CONFIG_TIMER
		gd->timer = NULL;
#endif
		/* TB710FU: dm_init_and_scan() itself hangs, and both of its halves
		 * take the live-tree path when CONFIG_OF_LIVE is on. That is now
		 * off, and the two halves are called separately with a log line
		 * before each and the return code after, so a hang names itself. */
		tb_screen_log("DM_INIT", 3);
		rc = dm_init(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		tb_screen_log("DM_SCAN", 3);
		rc = dm_scan(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);
"""
assert s.count(old) == 1, ("dm block", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: dm_init and dm_scan split and logged")
