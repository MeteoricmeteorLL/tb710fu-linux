import io

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

hdr = "\t/* TB710FU: boot the mainline kernel from UFS."
first = s.index(hdr)
second = s.index(hdr, first + 1)
print("block 1 at %d, block 2 at %d" % (first, second))

# drop the first copy entirely, keep the second
s = s[:first] + s[second:]

# now add the device/partition listing ahead of the remaining block
anchor = '\ttb_screen_log("BOOT: KERNEL PART", 3);'
assert s.count(anchor) == 1, s.count(anchor)

listing = '''	/* TB710FU: show the block devices and the partitions that matter before
	 * trying to read from them. The name lookup returned -ENOENT, so either
	 * the enumerated SCSI device is not the LUN holding the GPT, or the table
	 * was not parsed. Only boot/recovery/dtbo/vendor names are printed so the
	 * list stays short enough to read off the screen. */
	{
		int di, pi;

		for (di = 0; di < 4; di++) {
			struct blk_desc *d = blk_get_dev("scsi", di);
			struct disk_partition info;

			if (!d)
				continue;

			tb_screen_log("DEV INDEX", 3);
			tb_screen_log_hex((ulong)di, 3);
			tb_screen_log("DEV LBA BLKSZ", 3);
			tb_screen_log_hex((ulong)d->lba, 3);
			tb_screen_log_hex((ulong)d->blksz, 3);

			if (part_init(d))
				continue;

			for (pi = 1; pi <= 60; pi++) {
				if (part_get_info(d, pi, &info))
					break;
				if (!strncmp(info.name, "recovery", 8) ||
				    !strncmp(info.name, "boot", 4) ||
				    !strncmp(info.name, "dtbo", 4) ||
				    !strncmp(info.name, "vendor", 6)) {
					tb_screen_log(info.name, 3);
					tb_screen_log_hex((ulong)pi, 3);
					tb_screen_log_hex((ulong)info.start, 3);
				}
			}
		}
	}

'''
s = s.replace(anchor, listing + anchor, 1)

if "#include <string.h>" not in s:
    s = s.replace("#include <scsi.h>", "#include <scsi.h>\n#include <string.h>", 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: duplicate boot block removed, listing added")
