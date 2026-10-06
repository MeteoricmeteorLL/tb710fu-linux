#!/usr/bin/env python3
"""TB710FU U-Boot build #30 - load the kernel where it can actually live.

From build #29's screen the whole chain ran (KPART OK, READ KERNEL, GUNZIP,
SRC USED, DPART OK, READ DTB, FDT OPEN INTO, PATCH FDT 000000cc, CLI INIT,
BOOTI) and then nothing: no kernel output, no abort dump, no RETURNED. The
kernel was entered and died in the dark.

Cause, from the device tree we ship: its memory node is

    memory@a0000000 { device_type = "memory";
                      reg = <0x00 0xa0000000 0x00 0x00>; };

a zero-size bank. That is the placeholder XBL patches at boot, and every build
so far reloaded it from recovery_a so the placeholder came back. With no memory
the kernel dies inside setup_arch(), long before the first printk and long
before any console; the same tree would have taken 0x91000000 (where we put the
image) as being below memstart_addr as well. The earlier attempt that got as far
as "USB is silent" went through ABL, which loads the image at 0xA8000000 and
patches the node.

Three changes:
  1. load the image at 0xA8000000, i.e. inside the kernel's linear map;
  2. rebuild /memory from the tree ABL handed U-Boot (XBL patched that one) and
     put bootargs in /chosen, where the kernel reads them - an earlier build
     wrote them to the root node;
  3. hand over the way bootm does (cleanup_before_linux + armv8_switch_to_el2)
     instead of run_command_list("booti ..."), whose command interpreter,
     environment and image machinery this board's truncated bring-up never sets
     up.

And one new instrument: a post-mortem RAM probe. printk keeps its ring buffer in
the kernel's .bss and a warm reset does not clear DRAM, so the previous boot's
last words are still at the load address. Scan that window, put the text on the
screen, and leave a canary in it - the kernel clears .bss in head.S, so a wiped
canary on the next boot proves the kernel did execute, even if it printed
nothing.
"""
import io

U = "/home/meteor/u-boot-13r/"

# ---------------------------------------------------------------------------
# lib/initcall.c: the probe and the one-line log helper
# ---------------------------------------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

helpers = r'''

/* ---------------------------------------------------------------------------
 * TB710FU: one line per fact.
 *
 * The panel only holds about twenty lines at this pitch, so a label on one line
 * and its value on the next pushes some other fact off the top. Everything the
 * boot path reports goes through here instead.
 * ------------------------------------------------------------------------- */
void tb_logv(const char *label, ulong v)
{
	char buf[64];
	const char *hex = "0123456789abcdef";
	int i = 0, j;

	while (label[i] && i < 40) {
		buf[i] = label[i];
		i++;
	}
	buf[i++] = ' ';
	for (j = 0; j < 8; j++)
		buf[i++] = hex[(v >> (28 - 4 * j)) & 0xf];
	buf[i] = 0;
	tb_screen_log(buf, 3);
}

/* ---------------------------------------------------------------------------
 * TB710FU: post-mortem RAM probe.
 *
 * A kernel that dies before fbcon still leaves its last words behind: printk's
 * ring buffer lives in .bss, and a warm reset does not clear DRAM. On the next
 * boot that window is untouched (the load stops at the end of the image data,
 * which is where .bss begins), so it can be scanned and shown. With no UART
 * this is the only channel that can report a panic before the display is up.
 * ------------------------------------------------------------------------- */
u64 tb_ram_rd64(ulong addr)
{
	return *(volatile u64 *)addr;
}

/* Number of non-zero doublewords in [start, end): distinguishes a window the
 * kernel has written to (page tables, log ring) from untouched RAM. */
ulong tb_ram_nonzero(ulong start, ulong end)
{
	ulong a, n = 0;

	for (a = start; a + 8 <= end; a += 8) {
		if (tb_ram_rd64(a))
			n++;
	}
	return n;
}

/* Fill [start, end) with @val. Used to leave a canary in the kernel's .bss. */
void tb_ram_fill(ulong start, ulong end, u64 val)
{
	ulong a;

	start = (start + 7) & ~7UL;
	for (a = start; a + 8 <= end; a += 8)
		*(volatile u64 *)a = val;
}

/* First occurrence of @needle in [start, end), or 0. Stepping in words keeps
 * this tolerable over the tens of megabytes the kernel image spans. */
ulong tb_ram_find(const char *needle, ulong start, ulong end)
{
	int n = 0, i;
	ulong a;

	while (needle[n])
		n++;
	if (!n)
		return 0;
	for (a = start; a + n <= end; a += 8) {
		const char *p = (const char *)a;

		for (i = 0; i < n; i++) {
			if (p[i] != needle[i])
				break;
		}
		if (i == n)
			return a;
	}
	return 0;
}

static char tb_probe_txt[6144];
static int tb_probe_n;

/* Copy text out of RAM immediately after a hit: loading the kernel over the
 * region would destroy what is being read. The ring is packed records rather
 * than NUL-terminated strings, so stop at a run of unprintable bytes. */
void tb_ram_text(ulong addr, int max)
{
	int n = 0, run = 0;

	if (max > (int)sizeof(tb_probe_txt) - 1)
		max = sizeof(tb_probe_txt) - 1;
	while (n < max) {
		char c = *(volatile char *)addr++;

		if (c == '\n')
			run = 0;
		else if (c < 32 || c > 126) {
			if (++run > 8)
				break;
			c = ' ';
		} else
			run = 0;
		tb_probe_txt[n++] = c;
	}
	tb_probe_txt[n] = 0;
	tb_probe_n = n;
}

void tb_probe_dump(int scale)
{
	int i = 0;
	int per;

	if (!tb_probe_n)
		return;
	if (scale < 1)
		scale = 1;
	per = (TB_LOG_STRIDE - TB_LOG_X) / (8 * scale);
	while (i < tb_probe_n) {
		char line[240];
		int n = 0;

		while (n < per - 1 && i < tb_probe_n && tb_probe_txt[i] != '\n')
			line[n++] = tb_probe_txt[i++];
		if (i < tb_probe_n && tb_probe_txt[i] == '\n')
			i++;
		line[n] = 0;
		tb_screen_log(line, scale);
	}
}
'''

anchor = "void tb_mark(int idx)"
assert s.count(anchor) == 1, ("tb_mark", s.count(anchor))
s = s.replace(anchor, helpers.lstrip("\n") + "\n" + anchor, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: tb_logv + RAM probe helpers")

# ---------------------------------------------------------------------------
# common/board_r.c
# ---------------------------------------------------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old_decl = 'void tb_screen_log(const char *s, int scale);'
new_decl = ('void tb_screen_log(const char *s, int scale);\n'
            'void tb_logv(const char *label, ulong v);\n'
            'u64 tb_ram_rd64(ulong addr);\n'
            'ulong tb_ram_nonzero(ulong start, ulong end);\n'
            'void tb_ram_fill(ulong start, ulong end, u64 val);\n'
            'ulong tb_ram_find(const char *needle, ulong start, ulong end);\n'
            'void tb_ram_text(ulong addr, int max);\n'
            'void tb_probe_dump(int scale);\n'
            'int cleanup_before_linux(void);')
assert s.count(old_decl) == 1, ("decl", s.count(old_decl))
s = s.replace(old_decl, new_decl, 1)

if "#include <asm/system.h>" not in s:
    s = s.replace("#include <scsi.h>", "#include <scsi.h>\n#include <asm/system.h>", 1)

new_boot = r'''	/* TB710FU: boot the mainline kernel from UFS.
	 *
	 * ABL normally loads the kernel at 0xA8000000 and hands it a device tree
	 * whose /memory node it has already patched with the SMEM usable-RAM
	 * table. Bypassing ABL means doing both of those here, and both matter:
	 *
	 *  - the image has to land inside the kernel's own linear-map window. The
	 *    tree in recovery_a carries the placeholder XBL overwrites, "reg = <0
	 *    a0000000 0 0>", so a kernel loaded at 0x91000000 is below
	 *    memstart_addr: with no memory and no console it dies in setup_arch
	 *    without printing anything, which is what the last screen showed;
	 *  - /memory has to describe real RAM, and the only tree that does is the
	 *    one ABL handed U-Boot, so the node is copied from there.
	 *
	 * printk's ring buffer lives in the kernel's .bss and a warm reset leaves
	 * DRAM intact, so the previous boot's last words are still at the load
	 * address when this one starts. Scan that window before loading over it.
	 */
	{
		void *initfdt = tb_fdt_load();
		const void *memreg = NULL;
		int memlen = 0;
		ulong kload = 0xA8000000UL;	/* where ABL itself puts it */
		ulong rawdtb = kload + 0x3000000UL;	/* past the 44 MiB image */
		ulong kfdt = kload + 0x3800000UL;
		ulong srclen = 0;
		int rc;

		if (initfdt) {
			int off = fdt_path_offset(initfdt, "/memory");

			if (off >= 0)
				memreg = fdt_getprop(initfdt, off, "reg", &memlen);
		}
		if (!memreg || memlen < 16) {
			memreg = NULL;
			memlen = 0;
		}
		tb_logv("ABL MEM REGLEN", (ulong)memlen);

		{
			struct blk_desc *kdesc = NULL;
			struct disk_partition kinfo;
			int di;

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

			/* 16 MiB covers the 15 MiB compressed kernel; it is kept
			 * below /memory's start, which the kernel never looks at. */
			if (!rc) {
				rc = blk_dread(kdesc, kinfo.start, 0x8000,
					       (void *)0x90000000UL);
				tb_logv("KERNEL READ", (ulong)(unsigned int)rc);
			}

			if (!rc) {
				ulong img;

				srclen = 0x1000000;
				rc = gunzip((void *)kload, 0x4000000,
					    (void *)0x90000000UL, &srclen);
				tb_logv("GUNZIP", (ulong)(unsigned int)rc);
				tb_logv("SRC USED", srclen);

				/* The load above stopped at srclen, which is where
				 * .bss begins, so anything past it is whatever the
				 * previous boot left there. */
				img = tb_ram_rd64(kload + 0x10);
				if (img > srclen && img < 0x4000000) {
					ulong hit;

					/* 0x91000000 is where every build up to
					 * this one loaded the kernel. */
					hit = tb_ram_find("Linux version",
							  0x91000000UL + srclen,
							  0x91000000UL + img);
					tb_logv("PRV OLD HIT", hit);
					tb_logv("PRV OLD NZ",
						tb_ram_nonzero(0x91000000UL + srclen,
							       0x91000000UL + img));
					if (!hit)
						hit = tb_ram_find("Linux version",
								  kload + srclen,
								  kload + img);
					tb_logv("PRV NEW HIT", hit);
					if (hit)
						tb_ram_text(hit, 4000);
				}
			}
		}

		if (!rc) {
			struct blk_desc *ddesc = NULL;
			struct disk_partition dinfo;
			int di;

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
				rc = blk_dread(ddesc, dinfo.start, 0x1000,
					       (void *)rawdtb);
				tb_logv("DTB READ", (ulong)(unsigned int)rc);
			}

			/* The loaded tree is packed solid, so fdt_add_subnode()
			 * fails with -NOSPACE; patch a copy with a megabyte of
			 * slack and hand that to the kernel. */
			if (!rc) {
				rc = fdt_open_into((void *)rawdtb, (void *)kfdt,
						   0x100000);
				tb_logv("FDT OPEN", (ulong)(unsigned int)rc);
			}
		}

		if (!rc) {
			void *fdt = (void *)kfdt;
			u64 mreg[2 * 4];
			int nreg = 0, off, node;

			/* /memory: patch the node in place rather than adding a
			 * second one; the kernel takes any depth-1 node with
			 * device_type "memory". */
			off = -1;
			for (node = fdt_first_subnode(fdt, 0); node >= 0;
			     node = fdt_next_subnode(fdt, node)) {
				const char *nm = fdt_get_name(fdt, node, NULL);

				if (nm && !strncmp(nm, "memory", 6)) {
					off = node;
					break;
				}
			}
			if (off < 0)
				off = fdt_add_subnode(fdt, 0, "memory@a0000000");
			tb_logv("MEM NODE", (ulong)(unsigned int)off);

			if (off >= 0) {
				if (memlen >= 16) {
					nreg = memlen / 16;
					if (nreg > 4)
						nreg = 4;
					memcpy(mreg, memreg, nreg * 16);
				} else {
					/* Nothing to copy: one bank from what
					 * U-Boot parsed, clipped so that it does
					 * not claim the firmware area below the
					 * line ABL's own placement implies. */
					u64 base = gd->ram_base;
					u64 size = gd->ram_size;

					if (base < 0xa0000000ULL) {
						size -= 0xa0000000ULL - base;
						base = 0xa0000000ULL;
					}
					mreg[0] = cpu_to_fdt64(base);
					mreg[1] = cpu_to_fdt64(size);
					nreg = 1;
				}
				fdt_setprop_string(fdt, off, "device_type",
						   "memory");
				rc = fdt_setprop(fdt, off, "reg", mreg,
						 nreg * 16);
				tb_logv("MEM SET", (ulong)(unsigned int)rc);
				tb_logv("MEM0 ADDR", fdt64_to_cpu(mreg[0]));
				tb_logv("MEM0 SIZE", fdt64_to_cpu(mreg[1]));
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
				rc = fdt_setprop_string(fdt, off, "bootargs",
					"console=tty0 loglevel=8 "
					"ignore_loglevel nokaslr "
					"clk_ignore_unused pd_ignore_unused");
				tb_logv("ARGS SET", (ulong)(unsigned int)rc);
			}

			/* Last resort console: the panel ABL left scanning out,
			 * still live at 0xD5100000. */
			off = fdt_add_subnode(fdt, 0, "framebuffer@d5100000");
			tb_logv("FB NODE", (ulong)(unsigned int)off);
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
		}

		if (!rc) {
			ulong img = tb_ram_rd64(kload + 0x10);

			tb_logv("KLOAD", kload);
			/* head.S clears .bss long before anything can print, so
			 * a wiped canary next boot is proof the kernel ran. */
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
end = s.index('\ttb_screen_log("GD FLAGS", 3);')
s = s[:start] + new_boot + s[end:]

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: kernel loaded at 0xA8000000, /memory rebuilt, direct EL2 hand-off")
