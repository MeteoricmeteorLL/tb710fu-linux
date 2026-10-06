"""TB710FU: quiet boot -- strip the photographable-boot overhead from the
happy path.

The memboot build grew its diagnostics as "hold the screen so a phone can
photograph it" code, and that is what the boot spends its pre-kernel window on:

  * ~50 on-panel log lines per boot, each clearing 1600x56 px and rendering
    text at 3x scale ("drawn at 3x so a phone camera can read it") on the
    splash framebuffer -- tens of MiB of strongly ordered stores, the same
    store traffic the comments already blame for pushing boots past the
    watchdog window once;
  * the F-sequence's nine 3x hex renders of relocation state;
  * a 1 MiB byte-at-a-time FNV "oracle" hash of the gunzipped kernel;
  * a 16 MiB read of recovery_a for a 136 KB DTB head;
  * the initcall progress record written to the RAM mirror three times per
    entry (debug leftover).

None of this is needed to boot.  What IS needed on a board with no UART is
that a *failing* boot still says so, so the muting is centralized:

  * tb_quiet_ub = 1 (board_r.c): every tb_screen_log/tb_logv/tb_logv2/
    tb_probe_dump call goes quiet automatically, because they all funnel
    through tb_screen_log();
  * failures use tb_screen_log_force()/tb_screen_log_force_hex(), which
    ignore the mute: the ABORT handler in interrupts_64.c, BOOT ABORTED and
    the fallthrough jump, and the R-sequence failure line;
  * cheap colour bars (relocate_64.S, mark 5/1, banners, kmark_jump) stay;
  * the RAM forensics keep their (muted, trivial) reads except the oracle
    hash, which is gated off entirely;
  * the screen clear widens to the full log band in quiet mode, so no stale
    text from a previous verbose boot survives until the kernel repaints;
  * recovery_a is read back at its real flashed size (0x22 blocks, the
    0x22000-padded DTB head) instead of 0x1000 blocks.

Set tb_quiet_ub = 0 in board_r.c and rebuild to restore the fully
photographable boot.

Idempotent: exits without change if tb_quiet_ub already exists.
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
IC = "/home/meteor/u-boot-13r/lib/initcall.c"
BF = "/home/meteor/u-boot-13r/common/board_f.c"
IR = "/home/meteor/u-boot-13r/arch/arm/lib/interrupts_64.c"

s = load(BR)
if "tb_quiet_ub" in s:
    sys.exit("tb_quiet_ub already present - already patched?")

# ---------------------------------------------------------------------------
# A. board_r.c
# ---------------------------------------------------------------------------

patch(BR, [
    # A1. master switch + force declarations next to the other initcall.c
    #     prototypes
    ("""void tb_screen_log(const char *s, int scale);
void *tb_fdt_load(void);
""",
     """void tb_screen_log(const char *s, int scale);
void tb_screen_log_force(const char *s, int scale);
void tb_screen_log_force_hex(ulong v, int scale);
void *tb_fdt_load(void);

/* TB710FU: quiet boot.  1 = the happy path draws only the cheap colour bars
 * and the screen clear; the on-panel log (camera-scale text rendering), the
 * prev-boot RAM forensics and the oracle hash are skipped.  Failure sites
 * call the tb_screen_log_force*() variants, which ignore this flag, so a
 * dying boot still reports itself on the panel.  0 = the old fully
 * photographable boot. */
int tb_quiet_ub = 1;
""",
     "quiet switch declaration"),

    # A2. R-sequence result: log on failure or in verbose mode only
    ("""\t\trc = initcall_run_list(seq);
\t\ttb_screen_log(rc ? "R SEQ FAIL" : "R SEQ OK", 3);
\t\ttb_screen_log_hex((ulong)(unsigned int)rc, 4);
""",
     """\t\trc = initcall_run_list(seq);
\t\tif (rc || !tb_quiet_ub) {
\t\t\ttb_screen_log(rc ? "R SEQ FAIL" : "R SEQ OK", 3);
\t\t\ttb_screen_log_hex((ulong)(unsigned int)rc, 4);
\t\t}
""",
     "R SEQ result gate"),
])

# A3. the 1 MiB byte-at-a-time oracle hash: off in quiet mode
s = load(BR)
old_orcl = """\t\t\t\tif (!rc) {
\t\t\t\t\tu64 k8 = tb_ram_rd64(kload);
\t\t\t\t\tu32 got;
"""
new_orcl = """\t\t\t\t/* TB710FU: quiet boot skips the oracle hash: a megabyte of
\t\t\t\t * byte-at-a-time reads bought confidence in the read path
\t\t\t\t * during bring-up, not boot speed. */
\t\t\t\tif (!rc && !tb_quiet_ub) {
\t\t\t\t\tu64 k8 = tb_ram_rd64(kload);
\t\t\t\t\tu32 got;
"""
n = s.count(old_orcl)
if n != 1:
    sys.exit("board_r.c: ORCL block anchor count=%d (want 1)" % n)
s = s.replace(old_orcl, new_orcl)
save(BR, s)
print("board_r.c: ORCL hash gated")

# A4. recovery_a read: 0x22 blocks (the 0x22000-padded DTB head the flash
#     layout defines), not 0x1000 blocks = 16 MiB for a 136 KB tree
s = load(BR)
old_dtb = """\t\t\tif (!rc) {
\t\t\t\tbrc = blk_dread(ddesc, dinfo.start, 0x1000,
\t\t\t\t\t\t(void *)rawdtb);
\t\t\t\tif (brc != 0x1000)
\t\t\t\t\trc = -EIO;
\t\t\t}
"""
new_dtb = """\t\t\tif (!rc) {
\t\t\t\t/* TB710FU: the flashed DTB head is padded to 0x22000
\t\t\t\t * bytes; the old 0x1000-block read pulled 16 MiB off the
\t\t\t\t * device -- 120x the file -- on every boot. */
\t\t\t\tbrc = blk_dread(ddesc, dinfo.start, 0x22,
\t\t\t\t\t\t(void *)rawdtb);
\t\t\t\tif (brc != 0x22)
\t\t\t\t\trc = -EIO;
\t\t\t}
"""
n = s.count(old_dtb)
if n != 1:
    sys.exit("board_r.c: DTB read anchor count=%d (want 1)" % n)
s = s.replace(old_dtb, new_dtb)
save(BR, s)
print("board_r.c: recovery_a read right-sized to 0x22 blocks")

patch(BR, [
    # A5. BOOT ABORTED: forced past the mute
    ("""\ttb_screen_log("BOOT ABORTED", 3);
\ttb_screen_log_hex((ulong)(unsigned int)gd->flags, 3);
""",
     """\t/* TB710FU: forced past the quiet mute -- this is the one line a
\t * failed boot still gets to say. */
\ttb_screen_log_force("BOOT ABORTED", 3);
\ttb_screen_log_force_hex((ulong)(unsigned int)gd->flags, 3);
""",
     "BOOT ABORTED force"),

    # A6. fallthrough jump marker: forced
    ("""\t\ttb_screen_log("GO", 3);
\t\ttb_logv("ENTRY", (ulong)kentry);
""",
     """\t\ttb_screen_log_force("GO", 3);
\t\ttb_logv("ENTRY", (ulong)kentry);
""",
     "fallthrough GO force"),
])

# ---------------------------------------------------------------------------
# B. lib/initcall.c
# ---------------------------------------------------------------------------

patch(IC, [
    # B1. mute the funnel: every on-panel log goes through tb_screen_log
    ("""void tb_screen_log(const char *s, int scale)
{
\tchar buf[96];
\tchar *p = buf;

\t/* The call number on every line is what survives a bad photo. */
""",
     """/* TB710FU: quiet boot.  Every on-panel log funnels through here, so the
 * mute lives in this one place; failure paths call the _force variants. */
extern int tb_quiet_ub;

void tb_screen_log(const char *s, int scale)
{
\tchar buf[96];
\tchar *p = buf;

\tif (tb_quiet_ub)
\t\treturn;

\t/* The call number on every line is what survives a bad photo. */
""",
     "tb_screen_log mute"),

    # B2. force variants (ignore the mute) after the hex helper
    ("""void tb_screen_log_hex(ulong v, int scale)
{
\tchar txt[9];
\tchar *p = txt;

\ttb_put_hex(&p, v, 8);
\t*p = 0;
\ttb_screen_log(txt, scale);
}
""",
     """void tb_screen_log_hex(ulong v, int scale)
{
\tchar txt[9];
\tchar *p = txt;

\ttb_put_hex(&p, v, 8);
\t*p = 0;
\ttb_screen_log(txt, scale);
}

/* TB710FU: failure telemetry must ignore the quiet mute. */
void tb_screen_log_force(const char *s, int scale)
{
\tint save = tb_quiet_ub;

\ttb_quiet_ub = 0;
\ttb_screen_log(s, scale);
\ttb_quiet_ub = save;
}

void tb_screen_log_force_hex(ulong v, int scale)
{
\tint save = tb_quiet_ub;

\ttb_quiet_ub = 0;
\ttb_screen_log_hex(v, scale);
\ttb_quiet_ub = save;
}
""",
     "force variants"),

    # B3. widen the clear: in quiet mode nothing redraws the upper band
    ("""\tfor (row = 1100; row < 1990; row++) {
""",
     """\t/* TB710FU: in quiet mode nothing redraws the upper log band, so the
\t * clear has to start at its top or the previous boot's lines stay on
\t * the panel until the kernel repaints. */
\tfor (row = tb_quiet_ub ? TB_LOG_TOP : 1100; row < 1990; row++) {
""",
     "screen clear widen"),

    # B4. progress mirror: one record per initcall, not three
    ("""\t\ttb_progress(func);
\t\ttb_progress(func);
\t\ttb_progress(func);
""",
     """\t\ttb_progress(func);
""",
     "tb_progress single write"),
])

# ---------------------------------------------------------------------------
# C. board_f.c
# ---------------------------------------------------------------------------

patch(BF, [
    ("""\t{
\t\textern void tb_screen_fixed_hex(int y, ulong v, int scale);

\t\ttb_screen_fixed_hex(1400, (ulong)gd->ram_base, 3);
\t\ttb_screen_fixed_hex(1450, (ulong)gd->ram_size, 3);
\t\ttb_screen_fixed_hex(1500, (ulong)gd->mon_len, 3);
\t\ttb_screen_fixed_hex(1550, (ulong)gd->relocaddr, 3);
\t\ttb_screen_fixed_hex(1600, (ulong)gd->start_addr_sp, 3);
\t\ttb_screen_fixed_hex(1650, (ulong)gd->reloc_off, 3);
\t\ttb_screen_fixed_hex(1700, (ulong)(uintptr_t)gd->fdt_blob, 3);
\t\ttb_screen_fixed_hex(1750, (ulong)(uintptr_t)gd, 3);
\t\ttb_screen_fixed_hex(1800,
\t\t\t\t    (ulong)get_prev_bl_fdt_addr(), 3);
""",
     """\t{
\t\textern void tb_screen_fixed_hex(int y, ulong v, int scale);
\t\textern int tb_quiet_ub;

\t\t/* TB710FU: quiet boot skips the nine relocation-state renders;
\t\t * they were the F->R hang forensics, not boot steps. */
\t\tif (!tb_quiet_ub) {
\t\t\ttb_screen_fixed_hex(1400, (ulong)gd->ram_base, 3);
\t\t\ttb_screen_fixed_hex(1450, (ulong)gd->ram_size, 3);
\t\t\ttb_screen_fixed_hex(1500, (ulong)gd->mon_len, 3);
\t\t\ttb_screen_fixed_hex(1550, (ulong)gd->relocaddr, 3);
\t\t\ttb_screen_fixed_hex(1600, (ulong)gd->start_addr_sp, 3);
\t\t\ttb_screen_fixed_hex(1650, (ulong)gd->reloc_off, 3);
\t\t\ttb_screen_fixed_hex(1700, (ulong)(uintptr_t)gd->fdt_blob, 3);
\t\t\ttb_screen_fixed_hex(1750, (ulong)(uintptr_t)gd, 3);
\t\t\ttb_screen_fixed_hex(1800,
\t\t\t\t\t    (ulong)get_prev_bl_fdt_addr(), 3);
\t\t}
""",
     "F-seq fixed_hex gate"),
])

# ---------------------------------------------------------------------------
# D. arch/arm/lib/interrupts_64.c -- the abort handler is failure telemetry,
#    it must stay visible under the mute.
# ---------------------------------------------------------------------------

s = load(IR)
old_ext = """\t\textern void tb_screen_log(const char *s, int scale);
\t\textern void tb_screen_log_hex(ulong v, int scale);
"""
new_ext = """\t\textern void tb_screen_log_force(const char *s, int scale);
\t\textern void tb_screen_log_force_hex(ulong v, int scale);
"""
n = s.count(old_ext)
if n != 1:
    sys.exit("interrupts_64.c: extern anchor count=%d (want 1)" % n)
s = s.replace(old_ext, new_ext)

n1 = s.count('tb_screen_log("ABORT')
n2 = s.count("tb_screen_log_hex((ulong)pt_regs")
n3 = s.count("tb_screen_log_hex(far")
if n1 != 6 or n2 != 5 or n3 != 1:
    sys.exit("interrupts_64.c: call counts %d/%d/%d, want 6/5/1" % (n1, n2, n3))
s = s.replace('tb_screen_log("ABORT', 'tb_screen_log_force("ABORT')
s = s.replace("tb_screen_log_hex((ulong)pt_regs", "tb_screen_log_force_hex((ulong)pt_regs")
s = s.replace("tb_screen_log_hex(far", "tb_screen_log_force_hex(far")
save(IR, s)
print("interrupts_64.c: abort handler switched to forced logging")

print("quiet boot patch complete: rebuild with make ARCH=arm CROSS_COMPILE=aarch64-linux-gnu-")
