#!/usr/bin/env python3
"""Two U-Boot changes to go with the kernel's panel markers.

1. Clear the log band before the first line of the boot's own log. The panel is
   not cleared between boots, so lines from the previous boot survive in slots
   the current one has not reached yet - the photos show the block's tail
   (BSS ZEROED .. JUMP) above its head (DM INIT AND SCAN .. IMAGE SIZE), which
   is two boots' output stacked, and it reads as nonsense.

2. Draw a marker in the exact place the kernel's first milestone bar goes, just
   before the hand-off. If the kernel's red bar is missing next boot, this
   magenta one still being there says the panel was writable and the jump was
   reached - so the kernel's first instruction is what did not run.
"""
import io
import re

P = "/home/meteor/u-boot-13r/lib/initcall.c"
T = "\t"

s = io.open(P, encoding="utf-8", errors="surrogateescape").read()


def sub1(pat, rep, name):
    global s
    new, n = re.subn(pat, lambda m: rep, s, count=1)
    assert n == 1, ("EDIT FAILED: " + name, n)
    s = new


APPEND = """
/* Blank the bottom of the log band. The panel keeps whatever the last boot drew
 * there, and a line the current boot has not reached yet still shows the
 * previous boot's numbering, which reads as a mirage of a longer log. Only the
 * lower part is cleared: the lines above it are redrawn by this boot anyway,
 * and clearing the whole band would be ~21 MB of strongly ordered framebuffer
 * stores, which is the order of store traffic that has already pushed this
 * board's boot past its watchdog window once.
 */
void tb_screen_clear(void)
{
\tunsigned *fb = (unsigned *)TB_FB_BASE;
\tint row, col;

\tfor (row = 1100; row < 1990; row++) {
\t\tunsigned *line = fb + (ulong)row * TB_LOG_STRIDE;

\t\tfor (col = 0; col < 1720; col++)
\t\t\tline[col] = TB_COLOR_BLACK;
\t}
\ttb_log_y = TB_LOG_TOP;
\tif (tb_log_n < 14)
\t\ttb_log_n = 0;
}

/* Where the kernel paints its first milestone bar, in a colour it never uses:
 * if this one is still on the panel next boot, the jump happened and the panel
 * was writable - so what failed is the kernel's own first instruction. */
void tb_kmark_jump(void)
{
\tunsigned *fb = (unsigned *)TB_FB_BASE;
\tint row, col;

\tfor (row = 30; row < 90; row++) {
\t\tunsigned *line = fb + (ulong)row * TB_LOG_STRIDE + 2000;

\t\tfor (col = 0; col < 1200; col++)
\t\t\tline[col] = 0xFFFF00FF;
\t}
}
"""

s = s.rstrip("\n") + "\n" + APPEND
io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: tb_screen_clear() and tb_kmark_jump() added")

# ---------------------------------------------------------------------------
# board_r.c: call them
# ---------------------------------------------------------------------------
P2 = "/home/meteor/u-boot-13r/common/board_r.c"
b = io.open(P2, encoding="utf-8", errors="surrogateescape").read()

b2, n = re.subn(
    re.escape(T + T + 'tb_logv("UB EL", (ulong)current_el());\n'),
    lambda m: (T + T + "extern void tb_screen_clear(void);\n"
               + T + T + "extern void tb_kmark_jump(void);\n\n"
               + T + T + "tb_screen_clear();\n"
               + T + T + "tb_logv(\"UB EL\", (ulong)current_el());\n"),
    b, count=1)
assert n == 1, ("board_r tb_screen_clear", n)
b = b2

b2, n = re.subn(
    re.escape(T + T + T + 'tb_screen_log("JUMP", 3);\n'),
    lambda m: (T + T + T + "tb_kmark_jump();\n"
               + T + T + T + 'tb_screen_log("JUMP", 3);\n'),
    b, count=1)
assert n == 1, ("board_r tb_kmark_jump", n)
b = b2

io.open(P2, "w", encoding="utf-8", errors="surrogateescape").write(b)
print("board_r.c: log band cleared, jump marker drawn")
