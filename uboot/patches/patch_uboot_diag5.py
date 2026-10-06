#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #5 - localise the relocate_code hang.

Evidence: green+yellow+blue sentinels present, red absent. board_init_f
returned to crt0 but board_init_r was never entered, and reverting the DTS
framebuffer geometry did not change it. The suspect is the crt0 path:
    crt0 -> switch stack/gd -> relocate_code (copy image, fix .rela.dyn)
         -> relocation_return -> c_runtime_cpu_setup -> board_init_r

Instruments, all in one build:
  A) print ram_base/ram_size/mon_len/relocaddr/start_addr_sp at the end of
     board_init_f: if relocaddr lands inside 0xD5100000..0xD6A80000 then our own
     25.6 MiB banner wipe destroyed the relocation destination;
  B) tb_mark(N) sentinels in the assembly, so the first missing one names the
     failing step;
  C) the red "board_init_r entered" sentinel stays.
"""
import io

U = "/home/meteor/u-boot-13r/"


def save_regs(body):
    """Wrap a snippet so it cannot clobber the caller's registers."""
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
    body = "\tmov\tx0, #%d\n\tbl\ttb_mark\n" % n
    return "\n\t/* TB710FU: %s */\n" % comment + save_regs(body)


# --- 1) lib/initcall.c: tb_mark() ------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "void tb_mark(" not in s

helper = '''
/*
 * TB710FU: one coloured block per call site, laid out in a row low on the
 * screen (the assembly paths have no console and no driver model, so this is a
 * raw framebuffer write and nothing else). Colours in index order:
 *   0 green  1 yellow  2 blue  3 white  4 cyan  5 magenta  6 orange  7 red
 */
void tb_mark(int idx)
{
	static const unsigned cols[8] = {
		0xFF00FF00, 0xFFFFFF00, 0xFF0000FF, 0xFFFFFFFF,
		0xFF00FFFF, 0xFFFF00FF, 0xFFFF8000, 0xFFFF0000,
	};
	unsigned *fb = (unsigned *)TB_FB_BASE;
	unsigned col = cols[idx & 7];
	int r, c;

	for (r = 0; r < 150; r++) {
		unsigned *line = fb + (ulong)(1200 + r) * TB_LOG_STRIDE +
				 100 + (idx & 7) * 350;

		for (c = 0; c < 300; c++)
			line[c] = col;
	}
}
'''
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s.rstrip("\n") + "\n" + helper)
print("initcall.c: tb_mark added")

# --- 2) board_f.c: print the memory parameters -----------------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "tb_screen_fixed_hex" not in s

anchor = "	/* TB710FU: BLUE = board_init_f is about to return to crt0, which then"
assert s.count(anchor) == 1
tail = '''	/* TB710FU: the numbers that decide whether relocation can work at all,
	 * printed because the F->R hand-off hangs for reasons the DTB cannot
	 * explain. Rows top to bottom:
	 *   1100 ram_base  1150 ram_size  1200 mon_len
	 *   1250 relocaddr (relocation destination)  1300 start_addr_sp
	 * If relocaddr sits inside 0xD5100000..0xD6A80000 it was destroyed by our
	 * own banner wipe, which writes 25.6 MiB of framebuffer. */
	{
		extern void tb_screen_fixed_hex(int y, ulong v, int scale);

		tb_screen_fixed_hex(1100, (ulong)gd->ram_base, 3);
		tb_screen_fixed_hex(1150, (ulong)gd->ram_size, 3);
		tb_screen_fixed_hex(1200, (ulong)gd->mon_len, 3);
		tb_screen_fixed_hex(1250, (ulong)gd->relocaddr, 3);
		tb_screen_fixed_hex(1300, (ulong)gd->start_addr_sp, 3);
	}

'''
s = s.replace(anchor, tail + anchor, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: memory parameter printout added")

# --- 3) crt0_64.S sentinels ------------------------------------------------
p = U + "arch/arm/lib/crt0_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """	mov	x0, #0
	bl	board_init_f

"""
new = """	mov	x0, #0
	bl	board_init_f
""" + mark(0, "mark 0 = board_init_f returned to crt0") + "\n"
assert s.count(old) == 1, ("crt0 board_init_f", s.count(old))
s = s.replace(old, new, 1)

old = """	ldr	x0, [x18, #GD_RELOCADDR]	/* x0 <- gd->relocaddr */
	b	relocate_code
"""
new = """	ldr	x0, [x18, #GD_RELOCADDR]	/* x0 <- gd->relocaddr */
""" + mark(1, "mark 1 = stack and gd switched, about to relocate") + """
	b	relocate_code
"""
assert s.count(old) == 1, ("crt0 relocaddr", s.count(old))
s = s.replace(old, new, 1)

old = """relocation_return:
"""
new = """relocation_return:
""" + mark(5, "mark 5 = relocation finished, running relocated") + "\n"
assert s.count(old) == 1, ("crt0 relocation_return", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("crt0_64.S: marks 0, 1, 5 added")

# --- 4) relocate_64.S sentinels -------------------------------------------
p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """ENTRY(relocate_code)
	stp	x29, x30, [sp, #-32]!	/* create a stack frame */
	mov	x29, sp
"""
new = """ENTRY(relocate_code)
	stp	x29, x30, [sp, #-32]!	/* create a stack frame */
	mov	x29, sp
""" + mark(2, "mark 2 = relocate_code entered, stack frame live") + "\n"
assert s.count(old) == 1, ("relocate entry", s.count(old))
s = s.replace(old, new, 1)

old = """	b.lo	copy_loop
	str	x0, [sp, #24]
"""
new = """	b.lo	copy_loop
	str	x0, [sp, #24]
""" + mark(3, "mark 3 = image copied to the relocation address") + "\n"
assert s.count(old) == 1, ("relocate copy_loop", s.count(old))
s = s.replace(old, new, 1)

old = """relocate_done:
	switch_el x1, 3f, 2f, 1f
"""
new = """relocate_done:
""" + mark(4, "mark 4 = relocation fixups done") + """
	switch_el x1, 3f, 2f, 1f
"""
assert s.count(old) == 1, ("relocate done", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("relocate_64.S: marks 2, 3, 4 added")
