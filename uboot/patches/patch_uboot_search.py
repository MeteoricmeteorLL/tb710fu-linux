#!/usr/bin/env python3
"""TB710FU U-Boot build #27 - search every SCSI device for the partitions.

The listing showed only 20 MB and 32 MB LUNs with no partitions - but that loop
only looked at device indices 0..3. scsi_scan probes up to UFS_MAX_LUNS (0x7F),
so the device carrying the Android GPT is almost certainly at a higher index
that was never inspected.

Changes:
  * list every SCSI block device with a large capacity (skipping the small
    firmware LUNs), with its partition count and any boot/recovery/dtbo names;
  * find the kernel and device tree partitions by searching all devices for the
    name rather than assuming device 0.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# --- 1) replace the old listing block -------------------------------------
start = s.index("\t/* TB710FU: show the block devices and the partitions that matter")
end = s.index('tb_screen_log("BOOT: KERNEL PART", 3);', start)

new_listing = '''	/* TB710FU: which SCSI device carries the GPT? The earlier listing only
	 * looked at indices 0..3 and found 20 MB and 32 MB firmware LUNs holding
	 * no partitions; scsi_scan probes up to UFS_MAX_LUNS, so the device with
	 * the Android GPT is probably at a higher index. Print every large device
	 * and the boot partitions it holds. */
	{
		int di;

		for (di = 0; di < 128; di++) {
			struct blk_desc *d = blk_get_dev("scsi", di);
			struct disk_partition info;
			int pi, np = 0;

			if (!d || d->lba < 0x10000)
				continue;

			tb_screen_log("BIG DEV", 3);
			tb_screen_log_hex((ulong)di, 3);
			tb_screen_log("BIG DEV LBA", 3);
			tb_screen_log_hex((ulong)d->lba, 3);

			part_init(d);
			for (pi = 1; pi <= 64; pi++) {
				if (part_get_info(d, pi, &info))
					break;
				np++;
				if (!strncmp(info.name, "recovery", 8) ||
				    !strncmp(info.name, "boot", 4) ||
				    !strncmp(info.name, "dtbo", 4)) {
					tb_screen_log(info.name, 3);
					tb_screen_log_hex((ulong)pi, 3);
					tb_screen_log_hex((ulong)info.start, 3);
				}
			}

			tb_screen_log("BIG DEV NPART", 3);
			tb_screen_log_hex((ulong)np, 3);
		}
	}

'''
s = s[:start] + new_listing + s[end:]


def replace_region(text, head, tail, replacement):
    i = text.index(head)
    j = text.index(tail, i) + len(tail)
    return text[:i] + replacement + text[j:]


kernel_new = '''tb_screen_log("BOOT: KERNEL PART", 3);
		rc = -ENOENT;
		{
			/* Whichever device carries the GPT holds the partition; the
			 * SCSI device index is not necessarily 0 on UFS. */
			int di;

			for (di = 0; di < 128; di++) {
				struct blk_desc *d = blk_get_dev("scsi", di);
				struct disk_partition info;

				if (!d)
					continue;
				part_init(d);
				if (!part_get_info_by_name(d, "recovery_b",
							   &info)) {
					kdesc = d;
					kinfo = info;
					rc = 0;
					tb_screen_log("KDEV FOUND", 3);
					tb_screen_log_hex((ulong)di, 3);
					break;
				}
			}
		}
		tb_screen_log(rc ? "KPART FAIL" : "KPART OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);'''

dtb_new = '''tb_screen_log("BOOT: DTB PART", 3);
		rc = -ENOENT;
		{
			int di;

			for (di = 0; di < 128; di++) {
				struct blk_desc *d = blk_get_dev("scsi", di);
				struct disk_partition info;

				if (!d)
					continue;
				part_init(d);
				if (!part_get_info_by_name(d, "recovery_a",
							   &info)) {
					ddesc = d;
					dinfo = info;
					rc = 0;
					tb_screen_log("DDEV FOUND", 3);
					tb_screen_log_hex((ulong)di, 3);
					break;
				}
			}
		}
		tb_screen_log(rc ? "DPART FAIL" : "DPART OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);'''

s = replace_region(s, 'tb_screen_log("BOOT: KERNEL PART", 3);',
                   'tb_screen_log_hex((ulong)(unsigned int)rc, 3);', kernel_new)
s = replace_region(s, 'tb_screen_log("BOOT: DTB PART", 3);',
                   'tb_screen_log_hex((ulong)(unsigned int)rc, 3);', dtb_new)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: partitions found by searching every SCSI device")
