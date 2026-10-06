#!/usr/bin/env python3
"""TB710FU U-Boot build #25 - read the mainline kernel from UFS and booti it.

UFS works now: UFS OK, SCSI OK, SCSI COUNT = 1. So this build adds the actual
payload boot, each step logged on screen:

  1. blk_get_device_part_str("scsi", "0:vendor_boot_b", ...) - find the partition
     that will hold the gzipped kernel, and log its start LBA and size;
  2. blk_dread the compressed kernel to 0x90000000;
  3. gunzip to 0x91000000, logging the consumed and produced lengths;
  4. blk_dread the device tree from "0:dtbo_b" to 0x94000000;
  5. patch that tree: add /framebuffer@d5100000 so the kernel gets a console on
     the ABL splash framebuffer (there is no UART on this board), and set
     /chosen/bootargs with clk_ignore_unused/pd_ignore_unused, which mainline
     needs on Qualcomm so it does not switch off clocks it thinks are idle;
  6. run the booti command.

Partitions used: vendor_boot_b (100 MB, holds 15 MB of compressed kernel) and
dtbo_b (holds the 135 KB device tree). Both are backed up in backup/, and slot
_b's Android cannot boot anyway while boot_b carries U-Boot.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

for inc in ("#include <blk.h>", "#include <gzip.h>", "#include <part.h>",
            "#include <linux/libfdt.h>"):
    if inc not in s:
        anchor = "#include <scsi.h>"
        assert anchor in s
        s = s.replace(anchor, anchor + "\n" + inc, 1)

anchor = '\ttb_screen_log("GD FLAGS", 3);'
assert s.count(anchor) == 1

boot = '''	/* TB710FU: boot the mainline kernel from UFS.
	 *
	 * The compressed kernel lives in the vendor_boot_b partition and the device
	 * tree in dtbo_b, both written from the host with fastboot. U-Boot only
	 * has to read them, patch the tree so the kernel can print on the ABL
	 * splash framebuffer, and hand over with booti.
	 */
	{
		struct blk_desc *kdesc = NULL;
		struct disk_partition kinfo;
		int rc;

		tb_screen_log("BOOT: KERNEL PART", 3);
		rc = blk_get_device_part_str("scsi", "0:vendor_boot_b",
					     &kdesc, &kinfo, 1);
		tb_screen_log(rc ? "KPART FAIL" : "KPART OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		if (!rc) {
			tb_screen_log("KPART START LBA", 3);
			tb_screen_log_hex((ulong)kinfo.start, 3);
			tb_screen_log("KPART SIZE BLKS", 3);
			tb_screen_log_hex((ulong)kinfo.size, 3);

			/* 16 MiB is more than the 15 MiB compressed kernel. */
			tb_screen_log("BOOT: READ KERNEL", 3);
			rc = blk_dread(kdesc, kinfo.start, 0x8000, (void *)0x90000000UL);
			tb_screen_log_hex((ulong)(unsigned int)rc, 3);

			{
				ulong srclen = 0x1000000;

				tb_screen_log("BOOT: GUNZIP", 3);
				rc = gunzip((void *)0x91000000UL, 0x4000000,
					    (void *)0x90000000UL, &srclen);
				tb_screen_log_hex((ulong)(unsigned int)rc, 3);
				tb_screen_log("BOOT: SRC USED", 3);
				tb_screen_log_hex(srclen, 3);
			}
		}
	}

	{
		struct blk_desc *ddesc = NULL;
		struct disk_partition dinfo;
		int rc;

		tb_screen_log("BOOT: DTB PART", 3);
		rc = blk_get_device_part_str("scsi", "0:dtbo_b", &ddesc, &dinfo, 1);
		tb_screen_log(rc ? "DPART FAIL" : "DPART OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		if (!rc) {
			tb_screen_log("BOOT: READ DTB", 3);
			rc = blk_dread(ddesc, dinfo.start, 0x1000, (void *)0x94000000UL);
			tb_screen_log_hex((ulong)(unsigned int)rc, 3);

			/* Give the kernel a console: a simple-framebuffer node over the
			 * framebuffer ABL left behind, still being scanned out. */
			{
				void *fdt = (void *)0x94000000UL;
				u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };
				int off = fdt_add_subnode(fdt, 0,
							  "framebuffer@d5100000");

				tb_screen_log("BOOT: PATCH FDT", 3);
				tb_screen_log_hex((ulong)(unsigned int)off, 3);

				if (off >= 0) {
					fdt_setprop_string(fdt, off, "compatible",
							   "simple-framebuffer");
					fdt_setprop_u32(fdt, off, "width", 3200);
					fdt_setprop_u32(fdt, off, "height", 2000);
					fdt_setprop_u32(fdt, off, "stride", 12800);
					fdt_setprop_string(fdt, off, "format",
							   "a8r8g8b8");
					fdt_setprop(fdt, off, "reg", reg,
						    sizeof(reg));
				}

				rc = fdt_setprop_string(fdt, 0, "bootargs",
					"console=tty0 loglevel=8 "
					"clk_ignore_unused pd_ignore_unused");
				tb_screen_log_hex((ulong)(unsigned int)rc, 3);
			}

			tb_screen_log("BOOT: BOOTI", 3);
			run_command_list("booti 0x91000000 - 0x94000000", -1, 0);
			tb_screen_log("BOOT: RETURNED", 3);
		}
	}

'''
s = s.replace(anchor, boot + anchor, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: kernel-from-UFS boot path added")
