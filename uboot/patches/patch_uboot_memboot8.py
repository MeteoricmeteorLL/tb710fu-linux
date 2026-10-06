#!/usr/bin/env python3
"""Build #36 (memboot8): a control canary, so the instrument itself is checked.

v7's readings contradict each other: __log_buf (inside .bss) read 0, as if the
kernel's BSS clear had run, while __bss_start - also inside .bss - read
0x52585a50, neither the 5a5a5a5a canary nor zero. Two possibilities remain and
the current probe cannot tell them apart:

  * the kernel really does run and clear .bss, and something then writes a few
    words at __bss_start (a variable that legitimately lives there), or
  * the canary never lands where I think, or DRAM does not survive the reset
    (XBL trains DDR on every boot), in which case every "the kernel left this
    behind" conclusion in this session is unfounded.

Settle it with a second canary at an address nothing early touches - 512 MiB
above the load address, far from where the kernel's own allocations start - and
a pattern that cannot be confused with the .bss one. Then, one boot from now:

  control intact + .bss words zeroed  -> DRAM persists, the kernel cleared .bss
  control intact + .bss canary intact -> DRAM persists, the kernel never ran
  control gone                        -> DRAM does not persist after the reset,
                                         and the post-mortem channel is void

Also count the canary words and the zero words across the whole .bss window
instead of sampling one address.
"""
import io

U = "/home/meteor/u-boot-13r/"

# ---- 1) counting helper -------------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = "/* Fill [start, end) with @val. Used to leave a canary in the kernel's .bss. */"
new = '''/* Count doublewords equal to @val and equal to zero in [start, end). */
void tb_ram_count(ulong start, ulong end, u64 val, ulong *hits, ulong *zeros)
{
	ulong a, n = 0, z = 0;

	for (a = start; a + 8 <= end; a += 8) {
		u64 v = tb_ram_rd64(a);

		if (v == val)
			n++;
		else if (!v)
			z++;
	}
	if (hits)
		*hits = n;
	if (zeros)
		*zeros = z;
}

/* Fill [start, end) with @val. Used to leave a canary in the kernel's .bss. */'''
assert s.count(old) == 1, ("count", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)

# ---- 2) board_r.c ------------------------------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = "void tb_ram_fill(ulong start, ulong end, u64 val);"
new = '''void tb_ram_fill(ulong start, ulong end, u64 val);
void tb_ram_count(ulong start, ulong end, u64 val, ulong *hits, ulong *zeros);'''
assert s.count(old) == 1, ("decl", s.count(old))
s = s.replace(old, new, 1)

old = '''/* Exact kernel addresses for the early-boot ladder, same System.map. */
#define TB_K_BSS_START		0x2916000UL	/* __bss_start */
#define TB_K_LOG_BUF		0x292c170UL	/* __log_buf */
#define TB_K_SWAPPER_PGD	0x2013000UL	/* swapper_pg_dir */
#define TB_K_KIMAGE_VOFFSET	0x1f74000UL	/* kimage_voffset */'''
new = '''/* Exact kernel addresses from the same System.map. */
#define TB_K_BSS_START		0x2916000UL	/* __bss_start */

/* Control canary: 512 MiB above the load address, far from where the kernel's
 * own allocations start, with a pattern the .bss canary cannot be confused
 * with. If this one survives the reset but the .bss one does not, DRAM persists
 * and the kernel is what cleared .bss. */
#define TB_CTL_OFF		0x20000000UL
#define TB_CTL_VAL		0xa5a5a5a5a5a5a5a5ULL
#define TB_CTL_LEN		0x1000UL'''
assert s.count(old) == 1, ("defs", s.count(old))
s = s.replace(old, new, 1)

old = '''					/* Where the kernel got to, in the order it
					 * writes these: the BSS clear only runs once
					 * the MMU is on, the page tables and
					 * kimage_voffset only after __primary_switch,
					 * and the printk ring only moves once
					 * start_kernel runs. */
					tb_logv("PRV BSS W", tb_ram_rd64(kload +
							TB_K_BSS_START));
					tb_logv("PRV LOG W", tb_ram_rd64(kload +
							TB_K_LOG_BUF));
					tb_logv("PRV PGD W", tb_ram_rd64(kload +
							TB_K_SWAPPER_PGD));
					tb_logv("PRV KVOF W", tb_ram_rd64(kload +
							TB_K_KIMAGE_VOFFSET));
					tb_logv("PRV RB BITS", bits);'''
new = '''					ulong hits = 0, zeros = 0;

					/* What the previous boot left: the control
					 * canary says whether DRAM survives the reset
					 * at all, the .bss counts say whether the
					 * kernel's own clear ran (it does that in the
					 * PI stub, arch/arm64/kernel/pi/map_kernel.c). */
					tb_logv("PRV BSS W", tb_ram_rd64(kload +
							TB_K_BSS_START));
					tb_logv("PRV CTL W", tb_ram_rd64(kload +
							TB_CTL_OFF));
					tb_ram_count(b0, b1, 0x5a5a5a5a5a5a5a5aULL,
						     &hits, &zeros);
					tb_logv("PRV BSS 5A", hits);
					tb_logv("PRV BSS 00", zeros);
					tb_logv("PRV RB BITS", bits);'''
assert s.count(old) == 1, ("ladder", s.count(old))
s = s.replace(old, new, 1)

old = '''			if (img > srclen && img < 0x4000000)
				tb_ram_fill(kload + srclen, kload + img,
					    0x5a5a5a5a5a5a5a5aULL);'''
new = '''			if (img > srclen && img < 0x4000000)
				tb_ram_fill(kload + srclen, kload + img,
					    0x5a5a5a5a5a5a5a5aULL);
			tb_ram_fill(kload + TB_CTL_OFF,
				    kload + TB_CTL_OFF + TB_CTL_LEN,
				    TB_CTL_VAL);'''
assert s.count(old) == 1, ("ctlfill", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: control canary + .bss word counts")
