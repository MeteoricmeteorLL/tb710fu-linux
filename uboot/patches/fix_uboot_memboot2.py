#!/usr/bin/env python3
"""Build #30 fixes, from the screen of the first #30 run.

The log ended at

    1b ABL MEM REGLEN 00000000
    1c KPART 00000000
    1d KERNEL READ 00008000
    1e GD FLAGS
    1f 08010201

i.e. the block bailed out right after the kernel read and fell through to the
end of board_init_r. blk_dread() returns the number of blocks read (0x8000),
not zero, and the new `if (!rc)` gates treated that as a failure, so the gunzip,
the device tree, /memory and the hand-off were all skipped. The original code
only printed that value; the gates are new. Same mistake on the DTB read
(0x1000). Keep the block count in its own variable and compare it exactly.

Second finding: ABL MEM REGLEN was 0. board.c parses memory from the tree ABL
provides, then swaps gd->fdt_blob for U-Boot's own embedded tree (for the
video console), so tb_fdt_load() was handing back a tree that only has the
zero-size placeholder. Use get_prev_bl_fdt_addr(), which is the ABL one.

Also: label the fall-through "BOOT ABORTED" so a photo says it outright, log
whether the ABL tree was found, why a /memory node was rejected, and ram_base
so the fallback arithmetic can be checked.
"""
import io

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# --- 1) the ABL tree, not the embedded one -------------------------------
old = '''	{
		void *initfdt = tb_fdt_load();
		const void *memreg = NULL;'''
new = '''	{
		/* board.c parses RAM from the tree ABL provides and then swaps
		 * gd->fdt_blob for U-Boot's own embedded tree (for its video
		 * console), and the embedded one only has the zero-size
		 * placeholder; get_prev_bl_fdt_addr() is the ABL tree. */
		void *initfdt = (void *)(ulong)get_prev_bl_fdt_addr();
		const void *memreg = NULL;'''
assert s.count(old) == 1, ("initfdt", s.count(old))
s = s.replace(old, new, 1)

old = '''		if (initfdt) {
			int off = tb_memory_node(initfdt);

			if (off >= 0)
				memreg = fdt_getprop(initfdt, off, "reg", &memlen);
		}
		if (memreg && memlen >= 16) {'''
new = '''		if (initfdt && fdt_check_header(initfdt))
			initfdt = NULL;
		tb_logv("ABL FDT", (ulong)(uintptr_t)initfdt);
		if (initfdt) {
			int off = tb_memory_node(initfdt);

			if (off < 0)
				tb_logv("ABL MEM NO NODE", 0);
			else
				memreg = fdt_getprop(initfdt, off, "reg", &memlen);
		}
		if (memreg && memlen >= 16) {'''
assert s.count(old) == 1, ("ablfdt", s.count(old))
s = s.replace(old, new, 1)

old = '''			/* A node that adds up to no RAM is the zero-size
			 * placeholder XBL overwrites, not a memory map. */
			if (tot < 0x10000000)
				memreg = NULL;
		}'''
new = '''			/* A node that adds up to no RAM is the zero-size
			 * placeholder XBL overwrites, not a memory map. */
			if (tot < 0x10000000) {
				memreg = NULL;
				tb_logv("ABL MEM TOT", tot);
			}
		}'''
assert s.count(old) == 1, ("tot", s.count(old))
s = s.replace(old, new, 1)

# --- 2) blk_dread returns a block count, not an error ---------------------
old = '''			if (!rc) {
				rc = blk_dread(kdesc, kinfo.start, 0x8000,
					       (void *)0x90000000UL);
				tb_logv("KERNEL READ", (ulong)(unsigned int)rc);
			}'''
new = '''			if (!rc) {
				int brc = blk_dread(kdesc, kinfo.start, 0x8000,
						    (void *)0x90000000UL);

				/* blk_dread() returns the block count, not 0. */
				tb_logv("KERNEL READ", (ulong)(unsigned int)brc);
				if (brc != 0x8000)
					rc = -EIO;
			}'''
assert s.count(old) == 1, ("kdread", s.count(old))
s = s.replace(old, new, 1)

old = '''			if (!rc) {
				rc = blk_dread(ddesc, dinfo.start, 0x1000,
					       (void *)rawdtb);
				tb_logv("DTB READ", (ulong)(unsigned int)rc);
			}'''
new = '''			if (!rc) {
				int brc = blk_dread(ddesc, dinfo.start, 0x1000,
						    (void *)rawdtb);

				tb_logv("DTB READ", (ulong)(unsigned int)brc);
				if (brc != 0x1000)
					rc = -EIO;
			}'''
assert s.count(old) == 1, ("dread", s.count(old))
s = s.replace(old, new, 1)

# --- 3) say so when the kernel path bails --------------------------------
old = '''	tb_screen_log("GD FLAGS", 3);'''
new = '''	tb_screen_log("BOOT ABORTED", 3);'''
assert s.count(old) == 1, ("gdflags", s.count(old))
s = s.replace(old, new, 1)

# --- 4) ram_base, to check the fallback arithmetic -----------------------
old = '''			tb_logv("MEM SIZE", (ulong)gd->ram_size);'''
new = '''			tb_logv("RAM BASE", (ulong)gd->ram_base);
			tb_logv("MEM SIZE", (ulong)gd->ram_size);'''
assert s.count(old) == 1, ("rambase", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: ABL tree for /memory, blk_dread gates fixed, BOOT ABORTED label")
