#!/usr/bin/env python3
"""TB710FU U-Boot build #19 - skip initr_caches, and really save the fdt blob.

Build #18's index marker read 03. tb_progress's counter is a static in .bss, and
crt0 clears BSS after relocation, so the count restarts at 0 when the R sequence
begins - which makes 03 the *fourth* R entry: initr_trace, initr_reloc,
event_init, then initr_caches. So the hang is enable_caches(), the MMU/cache
re-initialisation, which no earlier build ever reached because the R sequence
never ran at all.

Also, build #18's fourth log line printed 00000000 for the saved fdt pointer:
that static was wiped by the same BSS clear, so the guard `if (saved)` skipped
the restore. Move it to a fixed physical address, 0x9b09d000, in the same RAM the
marker log already uses.

Changes:
  * build the truncated R sequence skipping initr_caches (U-Boot runs fine with
    the MMU and caches as ABL left them - the relocation itself ran with them
    off - and it only costs speed, which matters less than booting);
  * keep the fdt pointer in RAM at 0x9b09d000 so it survives the BSS clear, log
    both values, and restore the original.
"""
import io

U = "/home/meteor/u-boot-13r/"

# --- 1) lib/initcall.c: pointer no longer lives in .bss -------------------
p = U + "lib/initcall.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """/* TB710FU: the device tree pointer as the pre-relocation code last saw it. The
 * DTB lives in the copy reserve_fdt() makes outside the image, so the relocation
 * offset must never be added to it - this is what board_r.c restores. */
void *tb_fdt_blob_saved;"""
new = """/* TB710FU: the device tree pointer as the pre-relocation code last saw it. The
 * DTB lives in the copy reserve_fdt() makes outside the image, so the relocation
 * offset must never be added to it. It is kept at a fixed physical address
 * rather than in a variable: crt0 clears BSS after relocation, which wiped the
 * variable version and made board_r.c's restore a no-op. */
#define TB_FDT_SAVE_ADDR	0x9b09d000UL

void tb_fdt_save(void *blob)
{
	*(void **)TB_FDT_SAVE_ADDR = blob;
}

void *tb_fdt_load(void)
{
	return *(void **)TB_FDT_SAVE_ADDR;
}"""
assert s.count(old) == 1, ("fdt var", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("initcall.c: fdt pointer kept at a fixed address")

# --- 2) board_f.c: use the helper ----------------------------------------
p = U + "common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = """		{
			extern void *tb_fdt_blob_saved;

			tb_fdt_blob_saved = gd->fdt_blob;
		}"""
new = """		{
			extern void tb_fdt_save(void *blob);

			tb_fdt_save(gd->fdt_blob);
		}"""
assert s.count(old) == 1, ("save anchor", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: fdt blob saved via helper")

# --- 3) board_r.c: skip initr_caches, restore via helper -----------------
p = U + "common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """		for (i = 0; i < 63 && init_sequence_r[i]; i++) {
			if (init_sequence_r[i] == (init_fnc_t)initr_dm_devices)
				break;
			seq[n++] = init_sequence_r[i];
		}"""
new = """		for (i = 0; i < 63 && init_sequence_r[i]; i++) {
			if (init_sequence_r[i] == (init_fnc_t)initr_dm_devices)
				break;
			/* TB710FU: enable_caches() hangs on this board (the index
			 * marker stopped on it: it is the fourth R entry). U-Boot runs
			 * fine with the MMU and caches exactly as ABL left them - the
			 * relocation itself ran with them off - so this entry is
			 * skipped rather than waited for. */
			if (init_sequence_r[i] == (init_fnc_t)initr_caches)
				continue;
			seq[n++] = init_sequence_r[i];
		}"""
assert s.count(old) == 1, ("seq builder", s.count(old))
s = s.replace(old, new, 1)

old = """			extern void *tb_fdt_blob_saved;

			tb_screen_log("FDT PTR RELOCATED", 3);
			tb_screen_log_hex((ulong)(uintptr_t)gd->fdt_blob, 3);
			tb_screen_log("FDT PTR ORIGINAL", 3);
			tb_screen_log_hex((ulong)(uintptr_t)tb_fdt_blob_saved, 3);
			if (tb_fdt_blob_saved)
				gd->fdt_blob = tb_fdt_blob_saved;"""
new = """			extern void *tb_fdt_load(void);

			void *saved = tb_fdt_load();

			tb_screen_log("FDT PTR NOW", 3);
			tb_screen_log_hex((ulong)(uintptr_t)gd->fdt_blob, 3);
			tb_screen_log("FDT PTR SAVED", 3);
			tb_screen_log_hex((ulong)(uintptr_t)saved, 3);
			if (saved)
				gd->fdt_blob = saved;"""
assert s.count(old) == 1, ("restore anchor", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: initr_caches skipped, fdt pointer restored")
