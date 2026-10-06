#!/usr/bin/env python3
"""Build #32 (memboot4), from the screen of the third #30/v3 run.

What the screen said:

    1c PRV NEW HIT 00000000
    1d PRV NEW W0 52401a1a
    23 MEM0 ADDR 816e0000
    24 MEM0 SIZE 00320000

Three conclusions:

  * PRV NEW W0 is not the 5a5a5a5a5a5a5a5a canary that was written into .bss
    before the hand-off, and 0x52401a1a is about 1.38e9 ns - a printk record
    timestamp. The kernel ran. PRV NEW HIT missed only because the ring had
    wrapped past its first line, so the needles have to be the messages a dying
    kernel prints last, not "Linux version".
  * /memory came out as a single 3 MiB bank. XBL reports usable RAM as a run of
    small banks interleaved with its own carveouts (0x816e0000 + 0x320000 ends
    exactly at the xbl-dt-log carveout at 0x81a00000), so the kernel has to be
    given all of them, and bank 0 alone is useless.
  * the tree was built with CONFIG_FB_SIMPLE=y and CONFIG_FRAMEBUFFER_CONSOLE=y,
    so once the kernel has real memory, simplefb plus fbcon should put its own
    log on the panel - which is the fastest way out of the reboot-and-photograph
    loop. Nothing to rebuild for that; the framebuffer node is already added, and
    a /reserved-memory entry keeps the page allocator off it.

Also tighten the log pitch (16 * scale + 20 leaves room for only ~21 lines) and
drop the lines that are now dead weight, so the whole report fits.
"""
import io

U = "/home/meteor/u-boot-13r/"

# ---- 1) tighter line pitch -------------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = "\ttb_log_y += 16 * scale + 20;"
new = "\ttb_log_y += 16 * scale + 4;"
assert s.count(old) == 1, ("pitch", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)

# ---- 2) board_r.c ---------------------------------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = "int qcom_get_ram_banks(phys_addr_t *start, phys_size_t *size, int max);"
new = '''int qcom_get_ram_banks(phys_addr_t *start, phys_size_t *size, int max);

/* XBL reports usable RAM as many small banks, cut apart by its own carveouts. */
#define TB_RAM_BANKS	16
/* A device tree reg property holding that many (address, size) pairs. */
#define TB_RAM_REGS	(TB_RAM_BANKS * 2)'''
assert s.count(old) == 1, ("defs", s.count(old))
s = s.replace(old, new, 1)

new_boot = r'''	/* TB710FU: boot the mainline kernel from UFS.
	 *
	 * ABL normally loads the kernel at 0xA8000000 and hands it a device tree
	 * whose /memory node it has already patched with the SMEM usable-RAM
	 * table. Bypassing ABL means doing both here, and both matter:
	 *
	 *  - the image has to land inside the kernel's own linear-map window (the
	 *    tree in recovery_a carries the zero-size placeholder XBL overwrites,
	 *    and 0x91000000 - where earlier builds loaded it - is below
	 *    memstart_addr);
	 *  - /memory has to list every bank XBL calls usable, not one region: they
	 *    are small fragments around its carveouts (the first is 3 MiB), so a
	 *    single or truncated entry leaves the kernel with almost no RAM.
	 *
	 * printk's ring buffer lives in the kernel's .bss and a warm reset leaves
	 * DRAM intact, so the previous boot's log is still at the load address.
	 * Look for the messages a kernel prints as it dies: a wrapped ring has
	 * long overwritten the first line.
	 */
	{
		static const char *const late[] = {
			"Kernel panic",
			"No working init",
			"Run /init as init process",
			"Freeing unused kernel memory",
			"Linux version",
		};
		void *initfdt = (void *)(ulong)get_prev_bl_fdt_addr();
		const void *memreg = NULL;
		int memlen = 0;
		ulong kload = 0xA8000000UL;	/* where ABL itself puts it */
		ulong rawdtb = kload + 0x3000000UL;	/* past the 44 MiB image */
		ulong kfdt = kload + 0x3800000UL;
		ulong srclen = 0;
		phys_addr_t rb_start[TB_RAM_BANKS];
		phys_size_t rb_size[TB_RAM_BANKS];
		u64 mreg[TB_RAM_REGS];
		u64 rtot = 0;
		int nb = 0, i;
		int rc;

		/* The tree ABL handed over is the one XBL patched; U-Boot's own
		 * embedded tree only has the placeholder. */
		if (initfdt && fdt_check_header(initfdt))
			initfdt = NULL;
		if (initfdt) {
			int off = tb_memory_node(initfdt);

			if (off >= 0)
				memreg = fdt_getprop(initfdt, off, "reg", &memlen);
		}
		if (!memreg || memlen < 16)
			memlen = 0;

		if (memlen) {
			for (i = 0; i < memlen / 16 && i < TB_RAM_BANKS; i++) {
				u64 a = fdt64_to_cpu(tb_ram_rd64((ulong)memreg +
								 16 * i));
				u64 sz = fdt64_to_cpu(tb_ram_rd64((ulong)memreg +
								 16 * i + 8));

				if (!sz)
					continue;
				rb_start[nb] = a;
				rb_size[nb] = sz;
				rtot += sz;
				nb++;
			}
		}
		/* A node that adds up to no RAM is the placeholder, not a map. */
		if (nb < 1 || rtot < 0x10000000) {
			nb = qcom_get_ram_banks(rb_start, rb_size, TB_RAM_BANKS);
			rtot = 0;
			for (i = 0; i < nb; i++)
				rtot += rb_size[i];
		}
		tb_logv("RAM BANKS", (ulong)nb);
		tb_logv("RAM TOT", (ulong)rtot);
		for (i = 0; i < nb && i < 2; i++) {
			tb_logv(i ? "BANK1 START" : "BANK0 START", (ulong)rb_start[i]);
			tb_logv(i ? "BANK1 SIZE" : "BANK0 SIZE", (ulong)rb_size[i]);
		}

		{
			struct blk_desc *kdesc = NULL;
			struct disk_partition kinfo;
			int di, brc;

			/* part_get_info_by_name() returns -ENOENT even though the
			 * name shows up in the listing, so compare names directly
			 * with the same call the listing uses. */
			rc = -ENOENT;
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
						break;
					}
				}
			}
			tb_logv("KPART", (ulong)(unsigned int)rc);

			/* 16 MiB covers the 15 MiB compressed kernel, and it is kept
			 * below /memory's start, which the kernel never looks at. */
			if (!rc) {
				brc = blk_dread(kdesc, kinfo.start, 0x8000,
						(void *)0x90000000UL);
				/* blk_dread() returns the block count, not 0. */
				tb_logv("KERNEL READ", (ulong)(unsigned int)brc);
				if (brc != 0x8000)
					rc = -EIO;
			}

			if (!rc) {
				ulong img;

				srclen = 0x1000000;
				rc = gunzip((void *)kload, 0x4000000,
					    (void *)0x90000000UL, &srclen);
				tb_logv("GUNZIP", (ulong)(unsigned int)rc);
				tb_logv("SRC USED", srclen);

				/* The load stopped at srclen, which is where .bss
				 * begins, so everything past it is the previous
				 * boot's kernel. */
				img = tb_ram_rd64(kload + 0x10);
				if (img > srclen && img < 0x4000000) {
					ulong b0 = kload + srclen;
					ulong b1 = kload + img;
					ulong hit = 0;
					int k;

					for (k = 0; k < 5 && !hit; k++)
						hit = tb_ram_find(late[k], b0, b1);
					tb_logv("PRV LOG HIT", hit);
					tb_logv("PRV LOG NZ", tb_ram_nonzero(b0, b1));
					tb_logv("PRV LOG W0", tb_ram_rd64(b0));
					if (hit)
						tb_ram_text(hit > b0 + 400 ?
							    hit - 400 : b0, 4000);
				}
			}
		}

		if (!rc) {
			struct blk_desc *ddesc = NULL;
			struct disk_partition dinfo;
			int di, brc;

			rc = -ENOENT;
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
						break;
					}
				}
			}
			tb_logv("DTB PART", (ulong)(unsigned int)rc);

			if (!rc) {
				brc = blk_dread(ddesc, dinfo.start, 0x1000,
						(void *)rawdtb);
				tb_logv("DTB READ", (ulong)(unsigned int)brc);
				if (brc != 0x1000)
					rc = -EIO;
			}

			/* The loaded tree is packed solid, so fdt_add_subnode()
			 * fails with -NOSPACE; patch a copy with a megabyte of
			 * slack and hand that to the kernel. */
			if (!rc)
				rc = fdt_open_into((void *)rawdtb, (void *)kfdt,
						   0x100000);
		}

		if (!rc) {
			void *fdt = (void *)kfdt;
			int off;

			/* /memory: patch the node in place, all banks at once; the
			 * kernel takes any depth-1 node with device_type "memory". */
			off = tb_memory_node(fdt);
			if (off < 0)
				off = fdt_add_subnode(fdt, 0, "memory@a0000000");
			if (off < 0)
				rc = off;
			else {
				for (i = 0; i < nb; i++) {
					mreg[2 * i] = cpu_to_fdt64(rb_start[i]);
					mreg[2 * i + 1] = cpu_to_fdt64(rb_size[i]);
				}
				fdt_setprop_string(fdt, off, "device_type",
						   "memory");
				rc = fdt_setprop(fdt, off, "reg", mreg,
						 nb * 16);
				tb_logv("MEM SET", (ulong)(unsigned int)rc);
			}
		}

		if (!rc) {
			void *fdt = (void *)kfdt;
			int off = fdt_path_offset(fdt, "/chosen");

			if (off < 0)
				off = fdt_add_subnode(fdt, 0, "chosen");
			if (off >= 0) {
				/* No UART on this board, so stdout-path would
				 * only add a console nobody can read. */
				fdt_delprop(fdt, off, "stdout-path");
				tb_logv("ARGS SET", (ulong)(unsigned int)
					fdt_setprop_string(fdt, off, "bootargs",
					"console=tty0 loglevel=8 "
					"ignore_loglevel nokaslr "
					"clk_ignore_unused pd_ignore_unused"));
			}

			/* Console on the panel ABL left scanning out, plus the
			 * reservation that keeps the page allocator off it: the
			 * splash buffer sits inside the RAM XBL reports. */
			off = fdt_add_subnode(fdt, 0, "framebuffer@d5100000");
			if (off >= 0) {
				u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };

				fdt_setprop_string(fdt, off, "compatible",
						   "simple-framebuffer");
				fdt_setprop_u32(fdt, off, "width", 3200);
				fdt_setprop_u32(fdt, off, "height", 2000);
				fdt_setprop_u32(fdt, off, "stride", 12800);
				fdt_setprop_string(fdt, off, "format",
						   "a8r8g8b8");
				fdt_setprop(fdt, off, "reg", reg, sizeof(reg));
			}
			tb_logv("FB NODE", (ulong)(unsigned int)off);

			off = fdt_path_offset(fdt, "/reserved-memory");
			if (off < 0) {
				off = fdt_add_subnode(fdt, 0, "reserved-memory");
				if (off >= 0) {
					fdt_setprop_u32(fdt, off,
							"#address-cells", 2);
					fdt_setprop_u32(fdt, off,
							"#size-cells", 2);
					fdt_setprop_empty(fdt, off, "ranges");
				}
			}
			if (off >= 0) {
				u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };
				int fn = fdt_add_subnode(fdt, off,
							 "framebuffer@d5100000");

				if (fn >= 0) {
					fdt_setprop(fdt, fn, "reg", reg,
						    sizeof(reg));
					fdt_setprop_empty(fdt, fn, "no-map");
				}
			}

			/* Not fatal: a tree without a console description still
			 * boots, and /memory is already in. */
			rc = 0;
		}

		if (!rc) {
			ulong img = tb_ram_rd64(kload + 0x10);

			tb_logv("KLOAD", kload);
			tb_logv("IMAGE SIZE", img);
			/* head.S clears .bss long before anything can print, so a
			 * canary left intact here next boot means the kernel never
			 * reached that far. Only fill a size that looks like the
			 * image just unpacked; a bogus header would otherwise
			 * scribble over all of RAM. */
			if (img > srclen && img < 0x4000000)
				tb_ram_fill(kload + srclen, kload + img,
					    0x5a5a5a5a5a5a5a5aULL);
			tb_logv("MEM SIZE", (ulong)gd->ram_size);
			tb_logv("UB RELOC", (ulong)gd->relocaddr);

			tb_probe_dump(2);

			tb_screen_log("JUMP", 3);
			/* The hand-off bootm makes, without the command
			 * interpreter, the environment or the image machinery,
			 * none of which this board's bring-up sets up. */
			cleanup_before_linux();
			armv8_switch_to_el2((u64)kfdt, 0, 0, 0,
					    (u64)kload, ES_TO_AARCH64);
		}
	}

'''

start = s.index("\t/* TB710FU: boot the mainline kernel from UFS.")
end = s.index('\ttb_screen_log("BOOT ABORTED", 3);')
s = s[:start] + new_boot + s[end:]

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: all SMEM banks in /memory, late-boot needles, tighter pitch")
