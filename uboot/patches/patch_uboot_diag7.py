#!/usr/bin/env python3
"""TB710FU U-Boot diagnostic build #7 - guard the relocation fixup loop.

Evidence: sentinels 0 (board_init_f returned), 2 (relocate_code entered) and
3 (image copied) appear; 4 (fixups done) and everything after it do not. So the
hang is inside the .rela.dyn fixup loop, which writes to (link address + offset).
The only difference from the build that used to reach board_init_r is image
size: 1,461,256 bytes worked, 1,466,816 hung - and ABL places its own DTB at a
fixed spot after the payload, so a bigger image can end up underneath it.

Two independent changes, and the skip counter tells them apart:
  a) shrink the image: 4 KiB CP437 font -> 1.5 KiB printable-ASCII font
     (still renders whole words);
  b) bounds-check every fixup write to the relocated copy, cap the loop, and
     print the number of skipped fixups and the iteration count.
If the build boots with skipped = 0, the size was the cause. If it boots with
skipped > 0, bogus fixup targets were. If it still hangs, the counters show how
far the loop got.
"""
import io
import re

U = "/home/meteor/u-boot-13r/"


def save_regs(body, regs=("x0, x1", "x2, x3", "x4, x5", "x9")):
    pre = "".join("\tstp\t%s, [sp, #-16]!\n" % r if "," in r
                  else "\tstr\t%s, [sp, #-16]!\n" % r for r in regs)
    post = "".join("\tldp\t%s, [sp], #16\n" % r if "," in r
                   else "\tldr\t%s, [sp], #16\n" % r for r in reversed(regs))
    return pre + body + post


# --- 1) build the reduced ASCII font from U-Boot's own font ----------------
src = io.open(U + "include/video_font_8x16.h", encoding="utf-8",
              errors="surrogateescape").read()
body = src[src.index("= {") + 3:src.index("};")]
vals = [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]{2}),", body)]
assert len(vals) == 4096, len(vals)

rows = []
for c in range(32, 127):
    g = vals[c * 16:(c + 1) * 16]
    rows.append("\t{" + ", ".join("0x%02x" % b for b in g) + "},")
font_tbl = ("static const unsigned char tb_font_ascii[95][16] = {\n"
            + "\n".join(rows) + "\n};\n")

# --- 2) lib/initcall.c: swap the 4 KiB font for the reduced one ------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
assert "#include <video_font_8x16.h>" in s
s = s.replace("#include <video_font_8x16.h>", "")
s = s.replace("#include <video_font_data.h>", "")

old_draw = """	for (i = 0; s[i]; i++) {
		const unsigned char *g =
			&video_fontdata_8x16[(unsigned char)s[i] * 16];"""
new_draw = """	for (i = 0; s[i]; i++) {
		unsigned char c = (unsigned char)s[i];
		const unsigned char *g;

		if (c < 32 || c > 126)
			c = '?';
		g = tb_font_ascii[c - 32];"""
assert s.count(old_draw) == 1, ("draw anchor", s.count(old_draw))
s = s.replace(old_draw, new_draw)

anchor = "/* lib/initcall.c */" if "/* lib/initcall.c */" in s else "void tb_screen_log_reset(void)"
i = s.index("void tb_screen_log_reset(void)")
s = s[:i] + font_tbl + "\n" + s[i:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: reduced 95-glyph ASCII font installed (1520 bytes)")

# --- 3) relocate_64.S: guarded, capped fixup loop with counters -----------
p = U + "arch/arm/lib/relocate_64.S"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """fixloop:
	ldp	x0, x1, [x2], #16	/* (x0,x1) <- (SRC location, fixup) */
	ldr	x4, [x2], #8		/* x4 <- addend */
	and	x1, x1, #0xffffffff
	cmp	x1, #R_AARCH64_RELATIVE
	bne	fixnext

	/* relative fix: store addend plus offset at dest location */
	add	x0, x0, x9
	add	x4, x4, x9
	str	x4, [x0]
fixnext:
	cmp	x2, x3
	b.lo	fixloop
"""
new = """fixloop:
	ldp	x0, x1, [x2], #16	/* (x0,x1) <- (SRC location, fixup) */
	ldr	x4, [x2], #8		/* x4 <- addend */
	and	x1, x1, #0xffffffff
	cmp	x1, #R_AARCH64_RELATIVE
	bne	fixnext

	/* relative fix: store addend plus offset at dest location */
	add	x0, x0, x9
	add	x4, x4, x9

	/* TB710FU: every fixup must land inside the relocated copy. Anything
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
fixnext:
	add	x12, x12, #1
	cmp	x12, x13
	b.hs	fixdone
	cmp	x2, x3
	b.lo	fixloop
fixdone:
"""
assert s.count(old) == 1, ("fixloop anchor", s.count(old))
s = s.replace(old, new, 1)

old = """	adrp	x2, __rel_dyn_start		/* x2 <- address bits [31:12] */
	add	x2, x2, :lo12:__rel_dyn_start	/* x2 <- address bits [11:00] */
	adrp	x3, __rel_dyn_end		/* x3 <- address bits [31:12] */
	add	x3, x3, :lo12:__rel_dyn_end	/* x3 <- address bits [11:00] */
"""
new = """	adrp	x2, __rel_dyn_start		/* x2 <- address bits [31:12] */
	add	x2, x2, :lo12:__rel_dyn_start	/* x2 <- address bits [11:00] */
	adrp	x3, __rel_dyn_end		/* x3 <- address bits [31:12] */
	add	x3, x3, :lo12:__rel_dyn_end	/* x3 <- address bits [11:00] */

	/* TB710FU: fixup loop state (see fixloop) */
	mov	x5, #0
	mov	x12, #0
	mov	x13, #0x100000
"""
assert s.count(old) == 1, ("fixloop bounds", s.count(old))
s = s.replace(old, new, 1)

# print the two counters after the loop, before the done label's caller
old = """relocate_done:
"""
new = """	/* TB710FU: show how many fixups were skipped and how many ran.
	 * Row 1050 = skipped, row 1080 = iterations. */
	stp	x0, x1, [sp, #-16]!
	stp	x2, x3, [sp, #-16]!
	mov	x0, #1050
	mov	x1, x5
	bl	tb_screen_hexline
	mov	x0, #1080
	mov	x1, x12
	bl	tb_screen_hexline
	ldp	x2, x3, [sp], #16
	ldp	x0, x1, [sp], #16

relocate_done:
"""
assert s.count(old) == 1, ("relocate_done", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("relocate_64.S: fixup loop guarded, capped, counters printed")

# --- 4) board_f.c: print ABL's own DTB address ---------------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		tb_screen_fixed_hex(1750, (ulong)(uintptr_t)gd, 3);"""
new = """		tb_screen_fixed_hex(1750, (ulong)(uintptr_t)gd, 3);
		tb_screen_fixed_hex(1800,
				    (ulong)get_prev_bl_fdt_addr(), 3);"""
assert s.count(old) == 1, ("board_f fdt print", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: ABL DTB address printed at row 1800")
