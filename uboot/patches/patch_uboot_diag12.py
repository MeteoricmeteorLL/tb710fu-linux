#!/usr/bin/env python3
"""TB710FU U-Boot build #12 - make the relocation fixup loop observable.

diag8/diag9 finished the fixup loop and ran board_init_r; diag11 (32 bytes
bigger, same guarded loop) reaches mark 3 "image copied" and then nothing, with
no log text. The guard cannot fault (targets are range checked) and the counter
cannot run away (x12 is capped), so guessing is done: draw a progress bar from
inside the loop itself. One pixel per 16 iterations on row 1150 - if the loop
stalls, the bar length says exactly where.

Also fix the cache-maintenance order: clean the D-cache before invalidating the
I-cache, which is what self-modifying code requires.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# --- 1) progress bar inside the fixup loop -------------------------------
old = """fixnext:
	add	x12, x12, #1
	cmp	x12, x13
	b.hs	fixdone
	cmp	x2, x3
	b.lo	fixloop
fixdone:
"""
new = """fixnext:
	add	x12, x12, #1

	/* TB710FU: progress bar. One pixel per 16 iterations on row 1150, so a
	 * stall inside this loop is visible as a bar that stops growing.
	 * x10 = framebuffer base, x11 = row offset, x8 = scratch. */
	tst	x12, #0xf
	b.ne	fixnobar
	movz	x10, #0xD510, lsl #16
	movz	x11, #0xE0A, lsl #12		/* 1150 * 12800 */
	add	x10, x10, x11
	lsr	x8, x12, #4
	lsl	x8, x8, #2
	str	wzr, [x10, x8]
fixnobar:
	cmp	x12, x13
	b.hs	fixdone
	cmp	x2, x3
	b.lo	fixloop
fixdone:
"""
assert s.count(old) == 1, ("fixnext anchor", s.count(old))
s = s.replace(old, new, 1)

# --- 2) cache order: clean D before invalidating I -----------------------
old = """	tbz	w0, #2, 5f	/* skip flushing cache if disabled */
	tbz	w0, #12, 4f	/* skip invalidating i-cache if disabled */
	ic	iallu		/* i-cache invalidate all */
	isb	sy
4:	ldp	x0, x1, [sp, #16]
"""
new = """	tbz	w0, #2, 5f	/* skip flushing cache if disabled */
4:	ldp	x0, x1, [sp, #16]
"""
assert s.count(old) == 1, ("cache order anchor", s.count(old))
s = s.replace(old, new, 1)

old = """	bl     __asm_flush_l3_dcache
"""
new = """	bl     __asm_flush_l3_dcache

	/* TB710FU: invalidate the i-cache *after* the d-cache has been written
	 * back, which is the order self-modifying code requires. */
	mrs	x0, sctlr_el1
	tbz	w0, #12, 9f
	ic	iallu
	isb	sy
9:
"""
assert s.count(old) == 1, ("l3 flush anchor", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("relocate_64.S: progress bar added, cache order corrected")
