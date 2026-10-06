#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #6 - fix my own instrumentation bug and
split the remaining gap.

diag5 lesson: my crt0 mark 1 sat between `adr lr, relocation_return` and
`b relocate_code`, and `bl tb_mark` overwrites x30 (= lr), so relocate_code
returned into crt0 and relocated over and over. The missing magenta mark was my
bug, not the real hang. Marks inside relocate_code are safe: x30 lives in the
function's own stack frame there.

Marks: 0 board_init_f returned, 2 relocate_code entered, 3 image copied,
4 fixups done, 6 after the EL/SCTLR switch, 7 after the cache flush,
5 relocation_return (running relocated), 8 after c_runtime_cpu_setup,
9 just before `b board_init_r`. The BSS clear sits between 8 and 9: if 8 shows
and 9 does not, the `str xzr,[x0],#8` loop ran away, which happens when
__bss_end is not what the relocation fixups think it is.

tb_mark is expanded to 16 distinct positions/colours, and extra globals are
printed at rows 1400+.
"""
import io

U = "/home/meteor/u-boot-13r/"


def save_regs(body, extra=""):
    pre = ("\tstp\tx0, x1, [sp, #-16]!\n"
           "\tstp\tx2, x3, [sp, #-16]!\n"
           "\tstp\tx4, x5, [sp, #-16]!\n"
           "\tstr\tx9, [sp, #-16]!\n" + extra)
    post = ("\tldr\tx9, [sp], #16\n"
            "\tldp\tx4, x5, [sp], #16\n"
            "\tldp\tx2, x3, [sp], #16\n"
            "\tldp\tx0, x1, [sp], #16\n")
    return pre + body + post


def mark(n, comment, extra_pre=""):
    body = "\tmov\tx0, #%d\n\tbl\ttb_mark\n" % n
    return "\n\t/* TB710FU: %s */\n" % comment + save_regs(body, extra_pre)


# --- 1) expand tb_mark to 16 positions ------------------------------------
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

	for (r = 0; r < 150; r++) {
		unsigned *line = fb + (ulong)(1200 + r) * TB_LOG_STRIDE +
				 100 + (idx & 15) * 180;

		for (c = 0; c < 160; c++)
			line[c] = col;
	}
}
'''
s = s[:start] + new_fn
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: tb_mark expanded to 16 slots")

# --- 2) relocate_64.S: marks 6 and 7 --------------------------------------
p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """0:	tbz	w0, #2, 5f	/* skip flushing cache if disabled */
"""
new = "0:" + mark(6, "mark 6 = EL switch done, SCTLR read") + """	tbz	w0, #2, 5f	/* skip flushing cache if disabled */
"""
assert s.count(old) == 1, ("reloc label 0", s.count(old))
s = s.replace(old, new, 1)

old = """	bl     __asm_flush_l3_dcache
5:	ldp	x29, x30, [sp],#32
"""
new = """	bl     __asm_flush_l3_dcache
""" + mark(7, "mark 7 = cache flush done, about to return") + """
5:	ldp	x29, x30, [sp],#32
"""
assert s.count(old) == 1, ("reloc flush", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("relocate_64.S: marks 6, 7 added")

# --- 3) crt0_64.S: drop the lr-clobbering mark 1, add marks 8 and 9 -------
p = U + "arch/arm/lib/crt0_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

i = s.index("\t/* TB710FU: mark 1 = stack and gd switched")
j = s.index("\tb\trelocate_code", i)
s = s[:i] + s[j:]
print("crt0_64.S: mark 1 removed (it clobbered lr)")

old = """	bl	c_runtime_cpu_setup		/* still call old routine */
"""
new = """	bl	c_runtime_cpu_setup		/* still call old routine */
""" + mark(8, "mark 8 = c_runtime_cpu_setup returned") + "\n"
assert s.count(old) == 1, ("crt0 c_runtime_cpu_setup", s.count(old))
s = s.replace(old, new, 1)

old = """	b	board_init_r			/* PC relative jump */
"""
new = mark(9, "mark 9 = BSS cleared, entering board_init_r") + """
	b	board_init_r			/* PC relative jump */
"""
assert s.count(old) == 1, ("crt0 board_init_r", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("crt0_64.S: marks 8, 9 added")

# --- 4) board_f.c: print more globals, at rows that cannot collide --------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		tb_screen_fixed_hex(1100, (ulong)gd->ram_base, 3);
		tb_screen_fixed_hex(1150, (ulong)gd->ram_size, 3);
		tb_screen_fixed_hex(1200, (ulong)gd->mon_len, 3);
		tb_screen_fixed_hex(1250, (ulong)gd->relocaddr, 3);
		tb_screen_fixed_hex(1300, (ulong)gd->start_addr_sp, 3);"""
new = """		tb_screen_fixed_hex(1400, (ulong)gd->ram_base, 3);
		tb_screen_fixed_hex(1450, (ulong)gd->ram_size, 3);
		tb_screen_fixed_hex(1500, (ulong)gd->mon_len, 3);
		tb_screen_fixed_hex(1550, (ulong)gd->relocaddr, 3);
		tb_screen_fixed_hex(1600, (ulong)gd->start_addr_sp, 3);
		tb_screen_fixed_hex(1650, (ulong)gd->reloc_off, 3);
		tb_screen_fixed_hex(1700, (ulong)(uintptr_t)gd->fdt_blob, 3);
		tb_screen_fixed_hex(1750, (ulong)(uintptr_t)gd, 3);"""
assert s.count(old) == 1, ("board_f numbers", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: 8 values printed at rows 1400-1750")

# --- 5) board_r.c: move the red sentinel out of the log's way -------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		for (r = 0; r < 200; r++) {
			unsigned *line = fb + (ulong)(800 + r) * 3200 + 700;

			for (c = 0; c < 400; c++)
				line[c] = 0xFFFF0000;
		}"""
new = """		for (r = 0; r < 180; r++) {
			unsigned *line = fb + (ulong)(200 + r) * 3200 + 2600;

			for (c = 0; c < 400; c++)
				line[c] = 0xFFFF0000;
		}"""
assert s.count(old) == 1, ("board_r red", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: red sentinel moved to rows 200-379 cols 2600-2999")
