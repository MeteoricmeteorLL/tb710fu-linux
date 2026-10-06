"""TB710FU: kill the pre-GUNZIP stall -- a minimal cached window for the
kernel decompress and .bss fill.

Board evidence (user photo of the panel, boot of 2026-10-02): the on-screen
log always sits at "1b INITRD MAGIC" for a long time before "1c GUNZIP"
appears, and the boot's SCTLR reads 0x30d00988: bit0 M=0, bit2 C=0, bit12
I=0 -- U-Boot runs this whole stage with the MMU and both caches off.

Inflating 15 MiB of Image.gz into 43 MiB over uncached DRAM (every store a
single-access write, every LZ77 back-reference a DRAM read) plus the 27 MiB
.bss zero fill is the multi-second-to-tens-of-seconds stall.

U-Boot's own dcache_enable() is not usable here: it calls mmu_setup(),
which builds page tables from the DT memory banks and hung this board
(that is why initr_caches is skipped in the R sequence).

So open the window by hand and keep it tiny:

  * a flat identity map in two 4 KiB tables at 0x9b080000 (the safe no-map
    RAM that already hosts the progress mirror and the F-sequence copy):
    512 x 1 GiB block entries, all Device except entry 2 (0x80000000-
    0xBFFFFFFF) Normal cacheable write-back.  Everything the window touches
    lives in that GiB: the compressed kernel at 0x90000000, the kernel and
    its decompression window at 0xA8000000..0xAC000000, the stack, U-Boot.
    Platform MMIO on sm8650 is all below 0x10000000 (GB0, Device), so no
    peripheral can be speculated through the Normal mappings.
  * no drawing, no block I/O and no SMEM read happen inside the window.
  * closing does a full clean+invalidate of the dcache before clearing
    CR_C/CR_M/CR_I, so DRAM ends up with exactly the bytes the uncached
    code would have written, then icache invalidate + TLB flush.
  * the window is also closed on the abort fallthrough, so no path can
    reach the kernel with a foreign MMU table live.

tb_mark(8) goes up before the window opens, tb_mark(9) after it closes:
a hang between the two bars localizes to the window itself.

Idempotent: exits without change if tb_cache_window already exists.
"""

import sys

def load(p):
    with open(p, encoding="utf-8", errors="surrogateescape", newline="") as f:
        s = f.read()
    if "\r" in s:
        sys.exit("%s: contains CR - refusing to patch" % p)
    return s

def save(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)

def patch(path, edits):
    s = load(path)
    orig = s
    for old, new, what in edits:
        n = s.count(old)
        if n != 1:
            sys.exit("%s: %s anchor count=%d (want 1)" % (path, what, n))
        s = s.replace(old, new)
    if s != orig:
        save(path, s)
        print("%s: %d edit(s) applied" % (path, len(edits)))
    else:
        print("%s: no change" % path)

BR = "/home/meteor/u-boot-13r/common/board_r.c"

s = load(BR)
if "tb_cache_window" in s:
    sys.exit("tb_cache_window already present - already patched?")

patch(BR, [
    # 1. the mmu.h inline helpers (set_ttbr_tcr_mair)
    ("""#include <asm/system.h>
""",
     """#include <asm/system.h>
#include <asm/armv8/mmu.h>
""",
     "mmu.h include"),

    # 2. the window implementation, parked with the other tb_* helpers
    ("""int tb_quiet_ub = 1;
void tb_logv(const char *label, ulong v);
""",
     """int tb_quiet_ub = 1;

/* TB710FU: a minimal cached window around the kernel decompress.
 *
 * The board boots U-Boot with the MMU and both caches off (SCTLR bit0/2/12
 * = 0) because U-Boot's own enable_caches() hangs: its mmu_setup() builds
 * page tables from the DT memory banks.  Inflating the Image.gz over
 * uncached DRAM - every output byte a single-access store, every LZ77
 * back-reference a DRAM read - plus the 27 MiB .bss fill is the long stall
 * before the GUNZIP log line.
 *
 * Flat identity map, two 4 KiB tables in the safe no-map RAM that already
 * hosts the progress mirror: 1 GiB block entries, Device everywhere except
 * entry 2 (0x80000000-0xBFFFFFFF, Normal write-back) - that GiB holds all
 * of the window's traffic: the compressed kernel, the decompression
 * buffers, the stack and U-Boot itself.  sm8650 platform MMIO lives below
 * 0x10000000 (Device GB0), so nothing peripheral is reachable from a
 * Normal mapping.  No drawing, no block I/O and no SMEM read happen inside
 * the window; closing does a full clean+invalidate first, so DRAM ends up
 * with exactly the bytes the uncached code would have written. */
#define TB_MMU_L0	0x9b080000UL
#define TB_MMU_L1	0x9b081000UL

static void tb_cache_window(int on)
{
	/* T0SZ=16 (walk starts at L0), TG0=4K, inner-shareable, inner+outer
	 * write-back for TTBR0, IPS 32 GB. */
	const u64 tcr = (1ULL << 48) | (1ULL << 46) | (1ULL << 13) |
			(1ULL << 12) | 16;
	/* attr0 = Normal WB read/write allocate, attr1 = Device nGnRE */
	const u64 mair = 0x00000000000004FFULL;

	if (on) {
		volatile u64 *l0 = (volatile u64 *)TB_MMU_L0;
		volatile u64 *l1 = (volatile u64 *)TB_MMU_L1;
		int i;

		for (i = 0; i < 512; i++) {
			/* valid | block | AF | EL1 RW | inner shareable */
			u64 e = ((u64)i << 30) | 0x743UL;

			/* AttrIndx 1 (Device) everywhere but GB2 */
			if (i != 2)
				e |= (1UL << 2);
			l1[i] = e;
		}
		l0[0] = ((u64)TB_MMU_L1 & 0x0000FFFFFFFFF000ULL) | 0x3UL;

		/* Anything a previous stage left in the cache or the TLB
		 * must not outlive this transition: the table walk reads
		 * DRAM through those lines. */
		__asm__ volatile("dsb sy; tlbi vmalle1; dsb sy; isb"
				 ::: "memory");
		invalidate_dcache_all();

		set_ttbr_tcr_mair(1, TB_MMU_L0, tcr, mair);
		set_sctlr(get_sctlr() | CR_M);
		set_sctlr(get_sctlr() | CR_C | CR_I);
		return;
	}

	/* Idempotent: the success path closes right after the .bss fill,
	 * the abort fallthrough closes again before its own jump. */
	if (!(get_sctlr() & CR_M))
		return;

	flush_dcache_all();
	set_sctlr(get_sctlr() & ~(CR_C | CR_M | CR_I));
	invalidate_icache_all();
	__asm__ volatile("dsb sy; tlbi vmalle1; dsb sy; isb" ::: "memory");
}

void tb_logv(const char *label, ulong v);
""",
     "tb_cache_window function"),

])

s = load(BR)
old_gz = """\t\t\tsrclen = 0x1000000;
\t\t\trc = gunzip((void *)kload, 0x4000000,
\t\t\t\t\t    (void *)0x90000000UL, &srclen);
"""
new_gz = """\t\t\tsrclen = 0x1000000;
\t\t\t/* TB710FU: bar 8 = cached window opening.  If the screen
\t\t\t * stops between bar 8 and bar 9, the window itself is what
\t\t\t * broke. */
\t\t\ttb_mark(8);
\t\t\ttb_cache_window(1);
\t\t\trc = gunzip((void *)kload, 0x4000000,
\t\t\t\t\t    (void *)0x90000000UL, &srclen);
"""
n = s.count(old_gz)
if n != 1:
    sys.exit("board_r.c: gunzip anchor count=%d (want 1)" % n)
s = s.replace(old_gz, new_gz)
save(BR, s)
print("board_r.c: window opened around gunzip")

s = load(BR)
old_fill = """\t\t\tif (img > srclen && img < 0x4000000)
\t\t\t\ttb_ram_fill(kload + srclen, kload + img, 0);
"""
new_fill = """\t\t\tif (img > srclen && img < 0x4000000)
\t\t\t\ttb_ram_fill(kload + srclen, kload + img, 0);
\t\t\t/* window off: the clean+invalidate above wrote every
\t\t\t * cached byte back, so DTB I/O, drawing and the jump run
\t\t\t * exactly as they did before the window existed */
\t\t\ttb_cache_window(0);
\t\t\ttb_mark(9);
"""
n = s.count(old_fill)
if n != 1:
    sys.exit("board_r.c: bss fill anchor count=%d (want 1)" % n)
s = s.replace(old_fill, new_fill)
save(BR, s)
print("board_r.c: window closed after the .bss fill")

patch(BR, [
    # 4. the abort fallthrough must never jump with the window's MMU live
    ("""\t\ttb_screen_log_force("GO", 3);
\t\ttb_logv("ENTRY", (ulong)kentry);
\t\ttb_logv("DTB", (ulong)dtb);
\t\ticache_disable();
""",
     """\t\ttb_screen_log_force("GO", 3);
\t\ttb_logv("ENTRY", (ulong)kentry);
\t\ttb_logv("DTB", (ulong)dtb);
\t\ttb_cache_window(0);
\t\ticache_disable();
""",
     "fallthrough window close"),
])

print("fastgunzip patch complete: rebuild with make ARCH=arm CROSS_COMPILE=aarch64-linux-gnu-")
