#!/usr/bin/env python3
"""TB710FU U-Boot build #28 - find partitions by comparing names directly.

Build #27's listing proves the big device is there and carries 64 partitions with
exactly the names we want (dtbo_b, recovery_b, recovery_a, boot_b), each with its
partition index and start LBA. Yet part_get_info_by_name() still returns -ENOENT.

So stop using it: iterate part_get_info() the way the listing does - which
provably reads those names - and compare with strcmp. Then read the kernel and
device tree from kinfo/dinfo.start and boot.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()


def replace_region(text, head, tail, replacement):
    i = text.index(head)
    j = text.index(tail, i) + len(tail)
    return text[:i] + replacement + text[j:]


kernel_new = '''tb_screen_log("BOOT: KERNEL PART", 3);
		rc = -ENOENT;
		{
			/* part_get_info_by_name() returns -ENOENT even though the name
			 * shows up in the listing, so compare names directly with the
			 * same call the listing uses. */
			int di;

			for (di = 0; di < 128 && rc; di++) {
				struct blk_desc *d = blk_get_dev("scsi", di);
				struct disk_partition info;
				int pi;

				if (!d)
					continue;
				part_init(d);
				for (pi = 1; pi <= 64; pi++) {
					if (part_get_info(d, pi, &info))
						break;
					if (!strcmp((const char *)info.name,
						    "recovery_b")) {
						kdesc = d;
						kinfo = info;
						rc = 0;
						tb_screen_log("KDEV FOUND", 3);
						tb_screen_log_hex((ulong)di, 3);
						break;
					}
				}
			}
		}
		tb_screen_log(rc ? "KPART FAIL" : "KPART OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);'''

dtb_new = '''tb_screen_log("BOOT: DTB PART", 3);
		rc = -ENOENT;
		{
			int di;

			for (di = 0; di < 128 && rc; di++) {
				struct blk_desc *d = blk_get_dev("scsi", di);
				struct disk_partition info;
				int pi;

				if (!d)
					continue;
				part_init(d);
				for (pi = 1; pi <= 64; pi++) {
					if (part_get_info(d, pi, &info))
						break;
					if (!strcmp((const char *)info.name,
						    "recovery_a")) {
						ddesc = d;
						dinfo = info;
						rc = 0;
						tb_screen_log("DDEV FOUND", 3);
						tb_screen_log_hex((ulong)di, 3);
						break;
					}
				}
			}
		}
		tb_screen_log(rc ? "DPART FAIL" : "DPART OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);'''

s = replace_region(s, 'tb_screen_log("BOOT: KERNEL PART", 3);',
                   'tb_screen_log_hex((ulong)(unsigned int)rc, 3);', kernel_new)
s = replace_region(s, 'tb_screen_log("BOOT: DTB PART", 3);',
                   'tb_screen_log_hex((ulong)(unsigned int)rc, 3);', dtb_new)

# log the size and block size of the device we picked, plus the partition start
old = '''			tb_screen_log("KPART START LBA", 3);
			tb_screen_log_hex((ulong)kinfo.start, 3);'''
new = '''			tb_screen_log("KPART START LBA", 3);
			tb_screen_log_hex((ulong)kinfo.start, 3);
			tb_screen_log("KDEV BLKSZ LBA", 3);
			tb_screen_log_hex((ulong)kdesc->blksz, 3);
			tb_screen_log_hex((ulong)kdesc->lba, 3);'''
assert s.count(old) == 1, ("start lba log", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: partitions looked up by explicit name comparison")
