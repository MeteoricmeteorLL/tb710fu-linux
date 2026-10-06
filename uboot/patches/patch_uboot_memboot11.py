#!/usr/bin/env python3
"""Build #39 (memboot11): zero the kernel's .bss instead of canarying it.

The canary was a diagnostic that turned out to be a poison. The kernel's own
clear of .bss happens in early_map_kernel() (arch/arm64/kernel/pi/map_kernel.c),
which is reached via head.S's __primary_switch - i.e. AFTER primary_entry has
already run record_mmu_state() and preserve_boot_args(), and cpufeature.c says
outright that a .bss variable (arm64_use_ng_mappings) is read by
create_init_idmap() before early_map_kernel() initialises it. With 0x5a5a5a5a
filling .bss, that variable is garbage, the early page tables get the wrong
attributes, and the kernel dies before it installs its own vectors - which is
why no abort ever appeared on screen.

That also explains the readings that contradicted each other: boot_args stayed
zero (died in the first few instructions) while .bss looked partly cleared
(early kernel writes mixed with whatever the canary left), differently every
boot, and a control run with no kernel kept the canary intact.

Fix: zero that range, so the kernel starts in the state its boot protocol
assumes. Everything else stays: full SMEM /memory, the disabled GENI UART, and
the probe, which now has a chance of finding real text in __log_buf and putting
the kernel's own log on the screen.

Also drop the second canary: it wrote 4 KiB at 0xC8000000, which is someone
else's memory if that address falls in a carveout.
"""
import io

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = '''			/* head.S clears .bss long before anything can print, so a
			 * canary left intact here next boot means the kernel never
			 * reached that far. Only fill a size that looks like the
			 * image just unpacked; a bogus header would otherwise
			 * scribble over all of RAM. */
			if (img > srclen && img < 0x4000000)
				tb_ram_fill(kload + srclen, kload + img,
					    0x5a5a5a5a5a5a5a5aULL);
			tb_ram_fill(kload + TB_CTL_OFF,
				    kload + TB_CTL_OFF + TB_CTL_LEN,
				    TB_CTL_VAL);'''
new = '''			/* .bss must be zero when the kernel starts: it only
			 * clears it in early_map_kernel(), after primary_entry
			 * has already run, and create_init_idmap() reads a .bss
			 * variable before that. Filling it with a canary - as
			 * earlier builds did - hands the early page-table code
			 * garbage and kills the kernel before it can print or
			 * even install its vectors. Zero it from the end of the
			 * image data to _end. Only that range: a bogus header
			 * field would otherwise scribble over all of RAM. */
			if (img > srclen && img < 0x4000000)
				tb_ram_fill(kload + srclen, kload + img, 0);
			tb_logv("BSS ZEROED", img > srclen ? img - srclen : 0);'''
assert s.count(old) == 1, ("zerofill", s.count(old))
s = s.replace(old, new, 1)

# the control canary definitions and fill are gone
old = '''
/* Control canary: 512 MiB above the load address, far from where the kernel's
 * own allocations start, with a pattern the .bss canary cannot be confused
 * with. If this one survives the reset but the .bss one does not, DRAM persists
 * and the kernel is what cleared .bss. */
#define TB_CTL_OFF		0x20000000UL
#define TB_CTL_VAL		0xa5a5a5a5a5a5a5a5ULL
#define TB_CTL_LEN		0x1000UL'''
assert s.count(old) == 1, ("ctldefs", s.count(old))
s = s.replace(old, "", 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: .bss zeroed instead of canaried")
