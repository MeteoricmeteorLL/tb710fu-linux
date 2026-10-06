#!/usr/bin/env python3
"""TB710FU U-Boot build #20 - reject misaligned fixup targets, print the first.

Build #19's abort dump decoded as: ESR 0x96000061 = data abort, DFSC 0x21 =
alignment fault, WnR = 1 (a write); FAR 0xffeab232, i.e. a target ending in 0x2,
not 8-byte aligned; x1 = 0x403 so the entry did claim R_AARCH64_RELATIVE; the PC
is in the relocation fixup loop. A real linker never emits a misaligned
relocation target, so the loop is reading something that is not a clean table.
The range guard let it through because it only checked bounds, not alignment.

Changes:
  * the guard now rejects targets that are not 8-byte aligned, counting them
    (x5) and remembering the first rejected target (x15), which is printed so it
    can be matched against the real table locally - a handful of rejects means a
    few stray entries, thousands means the table pointer is wrong;
  * the synchronous abort dump stops after the first fault instead of falling
    through to U-Boot's own handler, which faults again with no console and
    fills the screen with recursive dumps.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) relocate_64.S: alignment-aware guard + first-bad-target -----------
p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """	/* TB710FU: every fixup must land inside the relocated copy. Anything
	 * else means the relocation table or the image is damaged, and writing
	 * there takes the CPU off the rails, so skip it and count it.
	 * x6/x7 = dest start/end, x5 = skipped, x12 = iterations,
	 * x13 = iteration cap. All are caller-saved scratch here. */
	ldr	x6, [sp, #16]
	ldr	x7, [sp, #24]
	cmp	x0, x6
	b.lo	fixskip
	cmp	x0, x7
	b.hs	fixskip
	str	x4, [x0]
	b	fixnext
fixskip:
	add	x5, x5, #1
"""
new = """	/* TB710FU: a genuine fixup target is 8-byte aligned and inside the
	 * relocated copy. Build #19 hit an alignment fault on a target ending in
	 * 0x2, which a real relocation table never contains, so the loop is not
	 * reading a clean table - reject anything that fails either test, count
	 * it (x5) and remember the first rejected target (x15) for the screen.
	 * x6/x7 = dest start/end, x12 = iterations, x13 = iteration cap. */
	tst	x0, #7
	b.ne	fixskip
	ldr	x6, [sp, #16]
	ldr	x7, [sp, #24]
	cmp	x0, x6
	b.lo	fixskip
	cmp	x0, x7
	b.hs	fixskip
	str	x4, [x0]
	b	fixnext
fixskip:
	add	x5, x5, #1
	cbnz	x15, fixnext
	mov	x15, x0
"""
assert s.count(old) == 1, ("guard", s.count(old))
s = s.replace(old, new, 1)

old = """	mov	x5, #0
	mov	x12, #0
	mov	x13, #0x100000
"""
new = """	mov	x5, #0
	mov	x12, #0
	mov	x13, #0x100000
	mov	x15, #0
"""
assert s.count(old) == 1, ("loop state", s.count(old))
s = s.replace(old, new, 1)

old = """	mov	x0, #1080
	mov	x1, x12
	bl	tb_screen_hexline
	ldp	x2, x3, [sp], #16
	ldp	x0, x1, [sp], #16
"""
new = """	mov	x0, #1080
	mov	x1, x12
	bl	tb_screen_hexline

	/* row 1110: the first fixup target that was rejected (0 = none) */
	stp	x0, x1, [sp, #-16]!
	mov	x0, #1110
	mov	x1, x15
	bl	tb_screen_hexline
	ldp	x0, x1, [sp], #16

	ldp	x2, x3, [sp], #16
	ldp	x0, x1, [sp], #16
"""
assert s.count(old) == 1, ("prints", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("relocate_64.S: alignment-aware guard, first bad target printed")

# --- 2) interrupts_64.c: stop after the first abort ----------------------
p = U + "arch/arm/lib/interrupts_64.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		tb_screen_log("ABORT X1 ENTRY", 3);
		tb_screen_log_hex((ulong)pt_regs->regs[1], 3);
	}
"""
new = """		tb_screen_log("ABORT X1 ENTRY", 3);
		tb_screen_log_hex((ulong)pt_regs->regs[1], 3);

		/* Stop here. Falling through to U-Boot's own handler means printf and
		 * show_regs running with no console, which fault again and fill the
		 * screen with recursive dumps - build #19 showed about fifteen of
		 * them. Hanging keeps the first and only useful dump readable; the
		 * watchdog resets the board afterwards, and nothing wipes the panel. */
		for (;;)
			;
	}
"""
assert s.count(old) == 1, ("abort tail", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("interrupts_64.c: abort dump stops after the first fault")
