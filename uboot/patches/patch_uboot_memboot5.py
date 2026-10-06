#!/usr/bin/env python3
"""Build #33 (memboot5): read the tail of the previous kernel's log without
guessing at keywords, and stop a console nobody can read from hanging the boot.

The v4 screen gave the first measurement of a kernel that actually has RAM:
RAM BANKS 15, RAM TOT e649e000 (3.6 GiB), MEM SET 0 - but PRV LOG HIT was still
0, because the needles ("Kernel panic", "No working init", ...) only match if
the kernel got that far, and a kernel that hangs prints no such line.

Every printk record starts with an 8-byte nanosecond timestamp, so the largest
plausible timestamp in the window is the tail of the log. Find it and dump from
there: no keyword needed, and it lands on whatever the kernel was saying when it
stopped.

Also disable the GENI UART in the tree handed to the kernel. CONFIG_SERIAL_QCOM_
GENI_CONSOLE is on, there is no UART on this board to read it from, and a console
write into a block whose clocks are not running spins forever - which is exactly
the shape of "boots to ~1.4 s and stops with no panic".
"""
import io

U = "/home/meteor/u-boot-13r/"

# ---- 1) find the newest record in a window ------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = "static char tb_probe_txt[6144];"
new = '''/* The newest printk record in [start, end): every record begins with an 8-byte
 * nanosecond timestamp, so the largest plausible one is the tail of the log.
 * Once the ring has wrapped, the first line is long gone, so this is what
 * finds whatever the kernel was saying when it stopped - no keyword needed. */
ulong tb_ram_latest_log(ulong start, ulong end, ulong *ts)
{
	ulong a, best = 0;
	u64 bestv = 0;

	for (a = start; a + 8 <= end; a += 8) {
		u64 v = tb_ram_rd64(a);

		if (v > 100000000ULL && v < 100000000000ULL && v > bestv) {
			bestv = v;
			best = a;
		}
	}
	if (ts)
		*ts = (ulong)bestv;
	return best;
}

static char tb_probe_txt[6144];'''
assert s.count(old) == 1, ("probe_txt", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)

# ---- 2) board_r.c ------------------------------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = "void tb_probe_dump(int scale);"
new = "void tb_probe_dump(int scale);\nulong tb_ram_latest_log(ulong start, ulong end, ulong *ts);"
assert s.count(old) == 1, ("decl", s.count(old))
s = s.replace(old, new, 1)

old = '''					ulong hit = 0;
					int k;

					for (k = 0; k < 5 && !hit; k++)
						hit = tb_ram_find(late[k], b0, b1);
					tb_logv("PRV LOG HIT", hit);
					tb_logv("PRV LOG NZ", tb_ram_nonzero(b0, b1));
					tb_logv("PRV LOG W0", tb_ram_rd64(b0));
					if (hit)
						tb_ram_text(hit > b0 + 400 ?
							    hit - 400 : b0, 4000);'''
new = '''					ulong hit = 0, ts = 0, last;
					int k;

					for (k = 0; k < 5 && !hit; k++)
						hit = tb_ram_find(late[k], b0, b1);
					last = tb_ram_latest_log(b0, b1, &ts);
					tb_logv("PRV LOG HIT", hit);
					tb_logv("PRV LOG NZ", tb_ram_nonzero(b0, b1));
					tb_logv("PRV LOG W0", tb_ram_rd64(b0));
					tb_logv("PRV TS", ts);
					/* The newest record is where the kernel stopped,
					 * so prefer its neighbourhood over a keyword. */
					if (last)
						tb_ram_text(last > b0 + 200 ?
							    last - 200 : b0, 4000);
					else if (hit)
						tb_ram_text(hit > b0 + 400 ?
							    hit - 400 : b0, 4000);'''
assert s.count(old) == 1, ("probe", s.count(old))
s = s.replace(old, new, 1)

old = '''			tb_logv("FB NODE", (ulong)(unsigned int)off);'''
new = '''			tb_logv("FB NODE", (ulong)(unsigned int)off);

			/* No UART is wired up on this board, so a serial console
			 * can only hang the boot writing into a block whose clocks
			 * nobody enabled; the panel is the console. */
			{
				int u = -1;

				while ((u = fdt_node_offset_by_compatible(fdt, u,
						"qcom,geni-se-uart")) >= 0)
					fdt_setprop_string(fdt, u, "status",
							   "disabled");
				u = -1;
				while ((u = fdt_node_offset_by_compatible(fdt, u,
						"qcom,geni-uart")) >= 0)
					fdt_setprop_string(fdt, u, "status",
							   "disabled");
				tb_logv("UART DISABLED", 1);
			}'''
assert s.count(old) == 1, ("uartoff", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c/board_r.c: newest-record probe, GENI UART disabled")
