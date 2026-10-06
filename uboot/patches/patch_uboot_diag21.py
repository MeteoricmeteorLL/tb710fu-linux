#!/usr/bin/env python3
"""TB710FU U-Boot build #21 - log the address of every R-sequence entry.

State: relocation completes cleanly (the reject counter reads 0), board_init_r
runs, and the R sequence stops at index 05. initr_reloc_global_data() does not
touch gd->fdt_blob for OF_SEPARATE (only OF_EMBED does), so the mangled-pointer
theory is out, and initr_malloc only carves the malloc area - it never reads the
device tree. Rather than guess which entry index 05 is, log each entry's address.

tb_progress() is called by initcall_run_list() before every entry, so it can log
the function pointer. It is gated on GD_FLG_RELOC, which initr_reloc sets, so the
66 pre-relocation F-sequence entries stay silent and only the R sequence logs -
about fourteen lines, which fit on screen. The address is the relocated one;
subtract reloc_off (printed at the left edge) to get the link address and look it
up in the symbol table.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """	{
		char txt[3];
		char *q = txt;

		tb_put_hex(&q, idx & 0xff, 2);
		*q = 0;
		tb_fb_clear_at(8, 250, 2 * 26 + 4, 16 * 3, 3200, 3);
		tb_fb_char_at(8, 250, txt[0], 3200, 3);
		tb_fb_char_at(8 + 26, 250, txt[1], 3200, 3);
	}
"""
new = """	{
		char txt[3];
		char *q = txt;

		tb_put_hex(&q, idx & 0xff, 2);
		*q = 0;
		tb_fb_clear_at(8, 250, 2 * 26 + 4, 16 * 3, 3200, 3);
		tb_fb_char_at(8, 250, txt[0], 3200, 3);
		tb_fb_char_at(8 + 26, 250, txt[1], 3200, 3);
	}

	/* TB710FU: during the R sequence (post-relocation, GD_FLG_RELOC is set by
	 * initr_reloc) log the entry's runtime address. Subtract gd->reloc_off to
	 * get the link address and the symbol table names the function - so a hang
	 * is identified by a photo instead of by guessing entry indices. The 66
	 * pre-relocation F-sequence entries stay silent. */
	if (gd->flags & GD_FLG_RELOC) {
		char abuf[9];
		char *q = abuf;

		tb_put_hex(&q, (ulong)func, 8);
		*q = 0;
		tb_screen_log(abuf, 3);
	}
"""
assert s.count(old) == 1, ("index marker block", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: R-sequence entry addresses are logged")
