#!/usr/bin/env python3
"""Robustness fixes for build #30, applied after patch_uboot_memboot.py.

  * tb_ram_rd64() reads byte-wise: this runs with the MMU off, where a wide
    access to an unaligned address faults rather than being handled.
  * /memory in the tree ABL handed U-Boot carries a unit address too, so look
    it up by name, and reject a node whose banks add up to no RAM (that is the
    zero-size placeholder, not a memory map).
  * a bootargs or framebuffer-node failure must not stop the hand-off.
"""
import io

U = "/home/meteor/u-boot-13r/"

# ---- 1) byte-wise 64-bit read -------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = '''u64 tb_ram_rd64(ulong addr)
{
	return *(volatile u64 *)addr;
}'''
new = '''u64 tb_ram_rd64(ulong addr)
{
	u64 v = 0;
	int i;

	/* Byte at a time: this runs with the MMU off, where a wide access to an
	 * unaligned address faults instead of being handled by the hardware. */
	for (i = 0; i < 8; i++)
		v |= (u64)*(volatile unsigned char *)(addr + i) << (8 * i);
	return v;
}'''
assert s.count(old) == 1, ("rd64", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)

# ---- 2) board_r.c -------------------------------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = "int cleanup_before_linux(void);"
new = '''int cleanup_before_linux(void);

/* /memory carries a unit address ("memory@a0000000") in these trees, so
 * fdt_path_offset("/memory") misses it; look the node up by name. */
static int tb_memory_node(const void *fdt)
{
	int node;

	for (node = fdt_first_subnode(fdt, 0); node >= 0;
	     node = fdt_next_subnode(fdt, node)) {
		const char *nm = fdt_get_name(fdt, node, NULL);

		if (nm && !strncmp(nm, "memory", 6))
			return node;
	}
	return -1;
}'''
assert s.count(old) == 1, ("decl", s.count(old))
s = s.replace(old, new, 1)

old = '''		if (initfdt) {
			int off = fdt_path_offset(initfdt, "/memory");

			if (off >= 0)
				memreg = fdt_getprop(initfdt, off, "reg", &memlen);
		}
		if (!memreg || memlen < 16) {
			memreg = NULL;
			memlen = 0;
		}
		tb_logv("ABL MEM REGLEN", (ulong)memlen);'''
new = '''		if (initfdt) {
			int off = tb_memory_node(initfdt);

			if (off >= 0)
				memreg = fdt_getprop(initfdt, off, "reg", &memlen);
		}
		if (memreg && memlen >= 16) {
			u64 tot = 0;
			int i;

			for (i = 0; i < memlen / 16 && i < 4; i++)
				tot += fdt64_to_cpu(tb_ram_rd64(
					(ulong)memreg + (2 * i + 1) * 8));
			/* A node that adds up to no RAM is the zero-size
			 * placeholder XBL overwrites, not a memory map. */
			if (tot < 0x10000000)
				memreg = NULL;
		}
		if (!memreg)
			memlen = 0;
		tb_logv("ABL MEM REGLEN", (ulong)memlen);'''
assert s.count(old) == 1, ("memlookup", s.count(old))
s = s.replace(old, new, 1)

old = '''			int nreg = 0, off, node;

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
			if (off < 0)'''
new = '''			int nreg = 0, off;

			/* /memory: patch the node in place rather than adding a
			 * second one; the kernel takes any depth-1 node with
			 * device_type "memory". */
			off = tb_memory_node(fdt);
			if (off < 0)'''
assert s.count(old) == 1, ("memnodesearch", s.count(old))
s = s.replace(old, new, 1)

old = '''				if (memlen >= 16) {
					nreg = memlen / 16;
					if (nreg > 4)
						nreg = 4;
					memcpy(mreg, memreg, nreg * 16);
				} else {
					/* Nothing to copy: one bank from what
					 * U-Boot parsed, clipped so that it does
					 * not claim the firmware area below the
					 * line ABL's own placement implies. */'''
new = '''				if (memlen >= 16) {
					u64 tot = 0;
					int i;

					nreg = memlen / 16;
					if (nreg > 4)
						nreg = 4;
					memcpy(mreg, memreg, nreg * 16);
					for (i = 0; i < nreg; i++)
						tot += fdt64_to_cpu(tb_ram_rd64(
							(ulong)memreg +
							(2 * i + 1) * 8));
					if (tot < 0x10000000)
						nreg = 0;
				}
				if (!nreg) {
					/* One bank from what U-Boot parsed,
					 * clipped so that it does not claim the
					 * firmware area below the line ABL's own
					 * placement implies. */'''
assert s.count(old) == 1, ("memcopy", s.count(old))
s = s.replace(old, new, 1)

old = '''				rc = fdt_setprop_string(fdt, off, "bootargs",
					"console=tty0 loglevel=8 "
					"ignore_loglevel nokaslr "
					"clk_ignore_unused pd_ignore_unused");
				tb_logv("ARGS SET", (ulong)(unsigned int)rc);'''
new = '''				tb_logv("ARGS SET", (ulong)(unsigned int)
					fdt_setprop_string(fdt, off, "bootargs",
					"console=tty0 loglevel=8 "
					"ignore_loglevel nokaslr "
					"clk_ignore_unused pd_ignore_unused"));'''
assert s.count(old) == 1, ("bootargs", s.count(old))
s = s.replace(old, new, 1)

old = '''				fdt_setprop(fdt, off, "reg", reg, sizeof(reg));
			}
		}

		if (!rc) {
			ulong img = tb_ram_rd64(kload + 0x10);'''
new = '''				fdt_setprop(fdt, off, "reg", reg, sizeof(reg));
			}

			/* Neither of the two above is fatal: a tree with no
			 * console description still boots, and /memory is in. */
			rc = 0;
		}

		if (!rc) {
			ulong img = tb_ram_rd64(kload + 0x10);'''
assert s.count(old) == 1, ("nonfatal", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("edits applied")
