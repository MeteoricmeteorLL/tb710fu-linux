#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #8 - bars instead of blocks, finer marks.

Two things learned locally while reading the link map:
  * .rela.dyn sits at image offset 0x12F828..0x14B458 (4738 entries), i.e. just
    past __image_copy_end, and the fixup writes all land inside the copied range
    - so a damaged relocation table cannot be what kills the loop, and the
    earlier "cyan present/absent" reading was ambiguous (cyan and white sit next
    to each other and can look like one block in a phone photo);
  * the remaining suspects sit between relocate_done and relocation_return:
    the EL/SCTLR switch, the dcache flush, the L3 flush and the final `ret`.

So: tb_mark now draws a full-width horizontal bar, one distinct row and colour
per index, which cannot be confused by adjacency, and marks are added at every
step of that remaining path.
"""
import io

U = "/home/meteor/u-boot-13r/"


def save_regs(body):
    pre = ("\tstp\tx0, x1, [sp, #-16]!\n"
           "\tstp\tx2, x3, [sp, #-16]!\n"
           "\tstp\tx4, x5, [sp, #-16]!\n"
           "\tstr\tx9, [sp, #-16]!\n")
    post = ("\tldr\tx9, [sp], #16\n"
            "\tldp\tx4, x5, [sp], #16\n"
            "\tldp\tx2, x3, [sp], #16\n"
            "\tldp\tx0, x1, [sp], #16\n")
    return pre + body + post


def mark(n, comment):
    return ("\n\t/* TB710FU: %s */\n" % comment
            + save_regs("\tmov\tx0, #%d\n\tbl\ttb_mark\n" % n))


# --- 1) tb_mark -> horizontal bars ---------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
start = s.index("void tb_mark(int idx)")
new_fn = '''void tb_mark(int idx)
{
	static const unsigned cols[16] = {
		0xFF00FF00, 0xFFFFFF00, 0xFF0000FF, 0xFFFFFFFF,
		0xFF00FFFF, 0xFFFF00FF, 0xFFFF8000, 0xFFFF0000,
		0xFF008080, 0xFF80FF80, 0xFF8080FF, 0xFF808080,
		0xFF808000, 0xFF800080, 0xFF804000, 0xFF80FFFF,
	};
	unsigned *fb = (unsigned *)TB_FB_BASE;
	unsigned col = cols[idx & 15];
	int r, c;

	/* One horizontal bar per call site, its own row, so a bar can never be
	 * mistaken for its neighbour in a photo of the screen. Cols 400..3100
	 * keep clear of the hex values printed at the left edge. */
	for (r = 0; r < 36; r++) {
		unsigned *line = fb + (ulong)(1200 + (idx & 15) * 44 + r) *
				 TB_LOG_STRIDE + 400;

		for (c = 0; c < 2700; c++)
			line[c] = col;
	}
}
'''
s = s[:start] + new_fn
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: tb_mark draws per-index bars")

# --- 2) relocate_64.S: marks through the EL/cache/ret path ---------------
p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """4:	ldp	x0, x1, [sp, #16]
	bl	__asm_flush_dcache_range
	bl     __asm_flush_l3_dcache
"""
new = """4:	ldp	x0, x1, [sp, #16]
""" + mark(11, "mark 11 = about to flush the dcache over the copy") + """
	bl	__asm_flush_dcache_range
""" + mark(12, "mark 12 = dcache flush returned") + """
	bl     __asm_flush_l3_dcache
""" + mark(13, "mark 13 = l3 flush returned, about to ret") + "\n"
assert s.count(old) == 1, ("flush block", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("relocate_64.S: marks 11, 12, 13 added")

# --- 3) keep the counters, but only after the loop (they were fine) ------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
print("board_r.c untouched")
