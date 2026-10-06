#!/usr/bin/env python3
"""Build #34 (memboot6): read the kernel's printk ring through its own symbols.

v5's PRV TS was a false positive - a plausible-looking u64 inside binary data -
and the dump that followed printed one character. Guessing at addresses does not
work; the kernel's symbol table does. From the tree that built the flashed Image
(/home/meteor/linux, Image sha256 4acf7342...):

    _text                    0xffffffc080000000   off 0x0
    __bss_start              0xffffffc082916000   off 0x2916000
    __log_buf                0xffffffc08292c170   off 0x292c170  size 0x20000
    printk_rb_static         0xffffffc0823b4498   off 0x23b4498  in .data
    __bss_stop / _end                            off 0x29c5000 / 0x29e0000

and the initialized contents of printk_rb_static give the field offsets:

    0x00 count_bits 12        0x08 descs   0x10 infos
    0x30 text_data_ring.size_bits 17  -> 128 KiB
    0x38 text_data_ring.data  = __log_buf
    0x40 text_data_ring.head_lpos

head_lpos is a monotonically increasing byte position in the data ring (see
BLK0_LPOS in printk_ringbuffer.h), so `head_lpos & (size - 1)` is where the
newest text ends. Read that, step back 2 KiB through the ring (wrapping once)
and the kernel's last words come out - no keywords, no heuristics.

That also replaces the old window scans: the log is the signal, and the canary
still says whether the kernel ran at all.
"""
import io

U = "/home/meteor/u-boot-13r/"

# ---- 1) ring reader ----------------------------------------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = "void tb_probe_dump(int scale)"
new = '''/* Copy @len bytes of the circular buffer at @base (size @size, starting at ring
 * offset @start) into the probe buffer, wrapping once. printk's data ring holds
 * a record header between text blocks, so a run of unprintable bytes means "the
 * next record", not "the end" - keep going through it. */
void tb_ram_text_ring(ulong base, ulong size, ulong start, int len)
{
	int n = 0, run = 0;
	ulong i = start;

	if (len > (int)sizeof(tb_probe_txt) - 1)
		len = sizeof(tb_probe_txt) - 1;
	while (n < len) {
		char c = *(volatile char *)(base + (i & (size - 1)));

		i++;
		if (c == '\\n')
			run = 0;
		else if (c < 32 || c > 126) {
			if (++run > 64)
				break;
			c = ' ';
		} else
			run = 0;
		tb_probe_txt[n++] = c;
	}
	tb_probe_txt[n] = 0;
	tb_probe_n = n;
}

void tb_probe_dump(int scale)'''
assert s.count(old) == 1, ("probe_dump", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)

# ---- 2) board_r.c ------------------------------------------------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = "ulong tb_ram_latest_log(ulong start, ulong end, ulong *ts);"
new = '''ulong tb_ram_latest_log(ulong start, ulong end, ulong *ts);
void tb_ram_text_ring(ulong base, ulong size, ulong start, int len);

/* Where the kernel keeps its log, from the System.map of the tree that built the
 * flashed Image: printk_rb_static and the text_data_ring fields inside it. */
#define TB_KERNEL_TEXT_VA	0xffffffc080000000ULL	/* _text as linked */
#define TB_LOG_RB_OFF		0x23b4498UL	/* printk_rb_static */
#define TB_LOG_RB_SIZEBITS	0x30
#define TB_LOG_RB_DATA		0x38
#define TB_LOG_RB_HEAD		0x40
#define TB_LOG_TAIL_BYTES	2000'''
assert s.count(old) == 1, ("defs", s.count(old))
s = s.replace(old, new, 1)

old = '''					ulong hit = 0, ts = 0, last;
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
new = '''					ulong rb = kload + TB_LOG_RB_OFF;
					u64 dva = tb_ram_rd64(rb + TB_LOG_RB_DATA);
					u32 bits = (u32)tb_ram_rd64(rb +
							TB_LOG_RB_SIZEBITS);
					u64 head = tb_ram_rd64(rb + TB_LOG_RB_HEAD);

					tb_logv("PRV BSS W0", tb_ram_rd64(b0));
					tb_logv("PRV RB BITS", bits);
					/* The ring lives inside the image, so with
					 * nokaslr its virtual-to-physical offset is
					 * the image's own. */
					if (dva >= TB_KERNEL_TEXT_VA &&
					    bits >= 12 && bits <= 24) {
						ulong size = 1UL << bits;
						ulong dpa = kload + (ulong)(dva -
							TB_KERNEL_TEXT_VA);
						ulong off = (ulong)head & (size - 1);

						tb_logv("PRV RB OFF", off);
						tb_ram_text_ring(dpa, size,
								 (off + size -
								  TB_LOG_TAIL_BYTES) &
								 (size - 1),
								 TB_LOG_TAIL_BYTES);
					}'''
assert s.count(old) == 1, ("probe", s.count(old))
s = s.replace(old, new, 1)

# the needle table is no longer used
old = '''		static const char *const late[] = {
			"Kernel panic",
			"No working init",
			"Run /init as init process",
			"Freeing unused kernel memory",
			"Linux version",
		};
'''
assert s.count(old) == 1, ("late", s.count(old))
s = s.replace(old, "", 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: printk ring read via printk_rb_static / __log_buf offsets")
