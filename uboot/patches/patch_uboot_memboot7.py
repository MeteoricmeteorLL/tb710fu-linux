#!/usr/bin/env python3
"""Build #35 (memboot7): a progress ladder of exact kernel addresses.

v6 read printk_rb_static correctly (PRV RB BITS 17, i.e. the 128 KiB ring that
matches __log_buf's 0x20000), but head_lpos was still its initial value, and
setup_log_buf() keeps the static ring when no log_buf_len= is given. So the
kernel never emitted a single printk: it does not reach start_kernel's first
pr_notice(linux_banner).

PRV BSS W0 could not tell whether .bss was cleared either - that address is
_edata, the file-end padding just before __bss_start, which the kernel never
clears. Read exact symbols instead, in the order the kernel writes them:

    __bss_start     0x2916000   canary intact -> the BSS clear never ran
    swapper_pg_dir  0x2013000   zero -> __create_page_tables never built them
    kimage_voffset  0x1f74000   zero -> head.S never got that far
    __log_buf       0x292c170   zero with BSS cleared -> no printk yet
    head_lpos       0x23b44d8   initial -> start_kernel never ran

All offsets are from _text in the System.map of the tree that built the flashed
Image, and every one is 8-byte aligned.
"""
import io

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = '''#define TB_LOG_TAIL_BYTES	2000'''
new = '''#define TB_LOG_TAIL_BYTES	2000

/* Exact kernel addresses for the early-boot ladder, same System.map. */
#define TB_K_BSS_START		0x2916000UL	/* __bss_start */
#define TB_K_LOG_BUF		0x292c170UL	/* __log_buf */
#define TB_K_SWAPPER_PGD	0x2013000UL	/* swapper_pg_dir */
#define TB_K_KIMAGE_VOFFSET	0x1f74000UL	/* kimage_voffset */'''
assert s.count(old) == 1, ("defs", s.count(old))
s = s.replace(old, new, 1)

old = '''					tb_logv("PRV BSS W0", tb_ram_rd64(b0));
					tb_logv("PRV RB BITS", bits);'''
new = '''					/* Where the kernel got to, in the order it
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
assert s.count(old) == 1, ("ladder", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: early-boot ladder added")
