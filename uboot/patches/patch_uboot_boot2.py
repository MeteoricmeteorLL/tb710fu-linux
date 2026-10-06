#!/usr/bin/env python3
"""TB710FU U-Boot build #29 - make the DTB patchable, initialise the command
machinery before booti, and drop the now-redundant device listing.

From build #28's screen:
  * the DTB partition was found on SCSI device 4 and read (DPART OK), but
  * BOOT: PATCH FDT returned fffffff4 = -FDT_ERR_NOSPACE, so neither the
    simple-framebuffer node nor bootargs went in - the kernel would have no
    console. Fix: fdt_open_into() the tree into a 1 MiB scratch buffer so it has
    slack, patch that copy, and hand *that* to the kernel;
  * BOOT: BOOTI then aborted inside usb_stor_read with FAR = 0x48, i.e. a
    dereference through a stale/NULL pointer. booti goes through the command and
    image machinery, and the console/stdio init was deliberately removed from
    this board's bring-up (video probing hangs), so initialise the command
    machinery properly with cli_init() first.

Also drop the BIG DEV listing: it named the device that carries the GPT
(index 4), which is now known, and its lines push the important ones off screen.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# --- 1) drop the listing --------------------------------------------------
start = s.index("\t/* TB710FU: which SCSI device carries the GPT?")
end = s.index('tb_screen_log("BOOT: KERNEL PART", 3);', start)
s = s[:start] + s[end:]

# --- 2) includes ----------------------------------------------------------
if "#include <cli.h>" not in s:
    s = s.replace("#include <scsi.h>", "#include <scsi.h>\n#include <cli.h>", 1)

# --- 3) DTB: copy into a buffer with slack before patching ----------------
old = """			/* Give the kernel a console: a simple-framebuffer node over the
			 * framebuffer ABL left behind, still being scanned out. */
			{
				void *fdt = (void *)0x94000000UL;"""
new = """			/* The loaded tree is packed solid, so fdt_add_subnode() fails
			 * with -NOSPACE. Copy it into a scratch buffer with a megabyte
			 * of slack and patch that; the kernel gets the copy. */
			tb_screen_log("BOOT: FDT OPEN INTO", 3);
			{
				int orc = fdt_open_into((void *)0x94000000UL,
							(void *)0x95000000UL,
							0x100000);

				tb_screen_log_hex((ulong)(unsigned int)orc, 3);
			}

			/* Give the kernel a console: a simple-framebuffer node over the
			 * framebuffer ABL left behind, still being scanned out. */
			{
				void *fdt = (void *)0x95000000UL;"""
assert s.count(old) == 1, ("fdt patch head", s.count(old))
s = s.replace(old, new, 1)

# --- 4) boot the patched copy, after initialising the command machinery ---
old = """			tb_screen_log("BOOT: BOOTI", 3);
			run_command_list("booti 0x91000000 - 0x94000000", -1, 0);
			tb_screen_log("BOOT: RETURNED", 3);"""
new = """			tb_screen_log("BOOT: CLI INIT", 3);
			cli_init();

			tb_screen_log("BOOT: BOOTI", 3);
			run_command_list("booti 0x91000000 - 0x95000000",
					 -1, 0);
			tb_screen_log("BOOT: RETURNED", 3);"""
assert s.count(old) == 1, ("booti call", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: dtb slack, cli_init, listing removed")
