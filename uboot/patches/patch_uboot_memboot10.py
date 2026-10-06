#!/usr/bin/env python3
"""Build #38 (memboot10): a ladder of kernel writes that need no canary.

The control run proved the channel: with no kernel in the previous boot, .bss
came back full of the 5a5a canary (the dump showed a screen of 'Z'), so DRAM
survives the reset and XBL leaves it alone. Every reading of "it is zero, the
kernel must have done it" therefore stands: the kernel runs, its PI-stub memset
clears .bss (arch/arm64/kernel/pi/map_kernel.c), and it dies before the first
printk in start_kernel.

From the Image itself, three variables the early code writes are file-resident
zeros - not covered by the canary - so their runtime value is purely the
kernel's own write:

    boot_args       0x2395000   preserve_boot_args() stores x0..x3, x0 = the DTB
    idmap_pg_dir    0x2010000   create_idmap(): the first identity mapping
    kimage_voffset  0x1f74000   head.S, next to the page table creation

Read those, plus __bss_start and __log_buf (both inside .bss, so canary vs zero
tells whether the memset has run) and head_lpos (nonzero once printk runs), and
the exact instruction range the kernel stops in is bounded.

Drop the hangs: this build jumps to the kernel again.
"""
import io

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# 1) back to jumping
old = '''			/* Control run: no kernel, so the next boot's canary
			 * readings measure DRAM and the reset alone. */
			tb_screen_log("CONTROL RUN", 3);
			hang();

			tb_screen_log("JUMP", 3);'''
new = '''			tb_screen_log("JUMP", 3);'''
assert s.count(old) == 1, ("nojump", s.count(old))
s = s.replace(old, new, 1)

# 2) new read points
old = '''/* Exact kernel addresses from the same System.map. */
#define TB_K_BSS_START		0x2916000UL	/* __bss_start */'''
new = '''/* Exact kernel addresses from the same System.map. The first three are file
 * residents zeroed at link time and never covered by the canary, so whatever
 * they hold at runtime was written by the kernel itself. */
#define TB_K_BSS_START		0x2916000UL	/* __bss_start, in .bss */
#define TB_K_LOG_BUF		0x292c170UL	/* __log_buf, in .bss */
#define TB_K_BOOT_ARGS		0x2395000UL	/* boot_args[] */
#define TB_K_IDMAP_PGD		0x2010000UL	/* idmap_pg_dir[] */
#define TB_K_KIMAGE_VOFFSET	0x1f74000UL	/* kimage_voffset */'''
assert s.count(old) == 1, ("defs", s.count(old))
s = s.replace(old, new, 1)

old = '''					ulong hits = 0, zeros = 0;

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
new = '''					/* What the previous boot's kernel left,
					 * in the order that boot would have written
					 * it. The first three are zero in the file,
					 * so nonzero means the kernel got there. */
					tb_logv("PRV BOOT ARGS", tb_ram_rd64(kload +
							TB_K_BOOT_ARGS));
					tb_logv("PRV IDMAP PGD", tb_ram_rd64(kload +
							TB_K_IDMAP_PGD));
					tb_logv("PRV KIMG VOFF", tb_ram_rd64(kload +
							TB_K_KIMAGE_VOFFSET));
					tb_logv("PRV BSS W", tb_ram_rd64(kload +
							TB_K_BSS_START));
					tb_logv("PRV LOG W", tb_ram_rd64(kload +
							TB_K_LOG_BUF));
					tb_logv("PRV RB BITS", bits);'''
assert s.count(old) == 1, ("ladder", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: kernel-write ladder, jump restored")
