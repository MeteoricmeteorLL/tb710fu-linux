#!/usr/bin/env python3
"""TB710FU U-Boot build #18 - the hang is inside initcall_run_list(seq).

Build #17 numbered the log lines and that settled it: the log stops at line 02,
which is the entry-count line printed *before* initcall_run_list(seq) is called.
So the R sequence itself hangs partway - not the video probe (build #16 removed
it, unchanged), not my DT diagnostic lines (build #17 removed them, unchanged).

Three changes:
  1) tb_progress draws only its two hex index digits at a fixed spot, so the last
     index on screen names the entry that hung. It must stay cheap: this was
     ~27 MiB of framebuffer writes before, which alone pushed the boot past the
     watchdog window;
  2) before the sequence, log gd->fdt_blob as it is now and as it was saved at
     the end of board_init_f, so a mangled pointer is visible immediately;
  3) force gd->fdt_blob back to the saved value. Our DTB lives in the copy
     reserve_fdt() made *outside* the relocated image, so any relocation
     adjustment to that pointer is wrong - and initr_of_live builds the live
     tree from it, which is the prime suspect for the hang.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) lib/initcall.c: cheap index marker + saved fdt blob --------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

anchor = "static int tb_log_y = TB_LOG_TOP;"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + """

/* TB710FU: the device tree pointer as the pre-relocation code last saw it. The
 * DTB lives in the copy reserve_fdt() makes outside the image, so the relocation
 * offset must never be added to it - this is what board_r.c restores. */
void *tb_fdt_blob_saved;""", 1)

old = """	tb_progress(func);"""
new = """	tb_progress(func);"""
assert s.count(old) >= 1

# put the digits back into tb_progress, cheaply
old2 = """	/* TB710FU: the on-screen marker was removed. It redrew a 714x144 pixel
	 * "index:address" string for every F-sequence entry - about 27 MiB of
	 * strongly ordered framebuffer stores before relocation - and that alone
	 * was enough to run the boot past the watchdog window, which is what made
	 * the relocation look flaky. The RAM marker above still records the
	 * sequence, and lib/initcall.c's text log is the channel used for reading
	 * state off the screen.
	 */
"""
new2 = """	/* TB710FU: only the two index digits are drawn. The full 714x144 pixel
	 * "index:address" string cost about 27 MiB of strongly ordered framebuffer
	 * stores across the F sequence, which alone pushed the boot past the
	 * watchdog window and made the relocation look flaky. Two glyphs are
	 * enough: the last index on screen names the entry that hung. */
	{
		char txt[3];
		char *q = txt;

		tb_put_hex(&q, idx & 0xff, 2);
		*q = 0;
		tb_fb_clear_at(8, 250, 2 * 26 + 4, 16 * 3, 3200, 3);
		tb_fb_char_at(8, 250, txt[0], 3200, 3);
		tb_fb_char_at(8 + 26, 250, txt[1], 3200, 3);
	}
"""
assert s.count(old2) == 1, ("progress body", s.count(old2))
s = s.replace(old2, new2, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: index digits restored, tb_fdt_blob_saved added")

# --- 2) board_f.c: save the pre-relocation fdt pointer --------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
anchor = """		tb_screen_fixed_hex(1800,
				    (ulong)get_prev_bl_fdt_addr(), 3);"""
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + """
		/* TB710FU: remember the device tree pointer the pre-relocation code
		 * used, so board_r.c can undo any wrong relocation adjustment. */
		{
			extern void *tb_fdt_blob_saved;

			tb_fdt_blob_saved = gd->fdt_blob;
		}""", 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: fdt blob saved at end of board_init_f")

# --- 3) board_r.c: log and restore the pointer before the sequence --------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
anchor = "\t\ttb_screen_log_reset();"
assert s.count(anchor) == 1
s = s.replace(anchor, """\t\t{
			/* TB710FU: show the device tree pointer before and after the
			 * relocation, then force it back to the pre-relocation value.
			 * The DTB lives outside the relocated image, so the offset must
			 * not be applied to it. */
			extern void *tb_fdt_blob_saved;

			tb_screen_log("FDT PTR RELOCATED", 3);
			tb_screen_log_hex((ulong)(uintptr_t)gd->fdt_blob, 3);
			tb_screen_log("FDT PTR ORIGINAL", 3);
			tb_screen_log_hex((ulong)(uintptr_t)tb_fdt_blob_saved, 3);
			if (tb_fdt_blob_saved)
				gd->fdt_blob = tb_fdt_blob_saved;
		}
""" + anchor, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: fdt pointer logged and restored")
