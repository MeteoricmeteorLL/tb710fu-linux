#!/usr/bin/env python3
"""TB710FU U-Boot build #17 - number the log lines, drop my DT diagnostics.

Established: the R sequence runs (14 entries, return code 0), board_init_r is
reached, the relocation path is stable. The log then stops after about five
lines - and it stops at the same place whether or not the video probe exists,
so the video probe was never the blocker.

What sits between those two points is my own instrumentation: the FDT SRC /
FDT SIZE / FDT BLOB / FB NODE FOUND lines added in build #13. Those touch the
device tree (fdt_totalsize, ofnode_by_compatible) after relocation, where
gd->fdt_blob points at the copy reserve_fdt made - a copy outside the relocated
image - so a stale or wrongly adjusted pointer there is a plausible hang.

Two changes:
  * tb_screen_log() now prefixes every line with a two-digit hex line number, so
    a photo identifies the last line that ran even when the text is unreadable;
  * the DT diagnostic lines are removed. The storage probe is what matters.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) lib/initcall.c: prefix each log line with its number --------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """void tb_screen_log(const char *s, int scale)
{
	tb_fb_clear_at(TB_LOG_X, tb_log_y, 800,
		       16 * scale + 8, TB_LOG_STRIDE, 1);
	tb_screen_text(TB_LOG_X, tb_log_y, s, scale);
	tb_log_y += 16 * scale + 20;
}"""
new = """static ulong tb_log_n;

void tb_screen_log(const char *s, int scale)
{
	char buf[100];
	char *p = buf;

	/* Prefix every line with its call number: on a photo taken of the screen
	 * the text may be unreadable, but the number tells which line ran last. */
	tb_put_hex(&p, tb_log_n++, 2);
	*p++ = ' ';
	while (*s && (p - buf) < (int)sizeof(buf) - 2)
		*p++ = *s++;
	*p = 0;

	tb_fb_clear_at(TB_LOG_X, tb_log_y, 800,
		       16 * scale + 8, TB_LOG_STRIDE, 1);
	tb_screen_text(TB_LOG_X, tb_log_y, buf, scale);
	tb_log_y += 16 * scale + 20;
}"""
assert s.count(old) == 1, ("log fn", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: log lines numbered")

# --- 2) board_r.c: drop the DT diagnostics --------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

start = s.index('\ttb_screen_log("FDT SRC", 3);')
end = s.index('\ttb_screen_log("PROBE UFS", 3);')
s = s[:start] + '''\t/* TB710FU: the FDT SRC / FDT SIZE / FDT BLOB / FB NODE FOUND lines that
\t * used to sit here are gone. They read the device tree after relocation,
\t * where gd->fdt_blob points at the copy reserve_fdt() made outside the
\t * relocated image, and the log stops right about there - so they are a
\t * suspect, and they are only diagnostics anyway. Storage is what counts.
\t */
''' + s[end:]
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: DT diagnostics removed")
