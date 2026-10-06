#!/usr/bin/env python3
"""Build #31 (memboot3), from the screen of the second #30 run.

What the screen said:

    1e KPART 00000000        1f KERNEL READ 00008000   20 GUNZIP 00000000
    21 SRC USED 02915a00     22 PRV OLD HIT 00000000   23 PRV OLD NZ 00000000
    24 PRV NEW HIT 00000000  25 DTB PART 00000000     26 DTB READ 00001000
    27 FDT OPEN 00000000     28 MEM NODE 0000025c     29 MEM SET 00000000
    2a MEM0 ADDR a0000000    2b MEM0 SIZE 60000000    2c ARGS SET 00000000
    2d FB NODE 000000cc      2e KLOAD a8000000        2f IMAGE SIZE 029e0000
    30 RAM BASE 816e0000     31 MEM SIZE 7e920000     32 UB RELOC ffdca000
    33 JUMP

so the whole chain now runs and the hand-off happens. Three things follow:

  * MEM0 came from the fallback and was clipped to 0xA0000000, which threw away
    0.4 GiB: U-Boot's own span already starts above the firmware carveouts, so
    there is nothing to clip. Worse, ram_size is a span across whatever banks
    SMEM reported, so a single region would also claim any hole between them.
    Take the banks themselves - add an accessor for prevbl_ddr_banks[] - and log
    the count plus the first two, which also settles how much RAM this board
    really has (a span ending exactly at 4 GiB is suspicious).
  * PRV OLD NZ is 0, but that window is past the end of the gzipped image and was
    never written before, so zeros prove nothing. What does prove it is the
    canary written into the new window: head.S clears .bss long before anything
    can print, so 5a5a5a5a intact next boot means the kernel never cleared it.
    Log the first canary word.
  * the device tree in recovery_a still has no usable /memory of its own, so the
    log has to show which source was used: the ABL tree, the SMEM banks, or the
    span. Log the bank count before choosing.

And free the screen: the DM/UFS/SCSI lines are stable, so log them only on
failure (tb_logv), which keeps the whole boot report visible instead of pushing
the first lines off the top.
"""
import io

# ---- 1) expose the SMEM banks -------------------------------------------
p = "/home/meteor/u-boot-13r/arch/arm/mach-snapdragon/dram.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()
old = '''int dram_init_banksize(void)
{
	qcom_configure_bi_dram();

	return 0;
}'''
new = '''int dram_init_banksize(void)
{
	qcom_configure_bi_dram();

	return 0;
}

/* TB710FU: hand the SMEM usable-RAM table to the kernel boot path. ram_size is
 * a span across these banks, so handing the kernel one region would also claim
 * whatever hole sits between them (XBL keeps its own structures in one). */
int qcom_get_ram_banks(phys_addr_t *start, phys_size_t *size, int max)
{
	int i;

	for (i = 0; i < CONFIG_NR_DRAM_BANKS && i < max; i++) {
		start[i] = prevbl_ddr_banks[i].start;
		size[i] = prevbl_ddr_banks[i].size;
		if (!size[i])
			break;
	}
	return i;
}'''
assert s.count(old) == 1, ("dram_init_banksize", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)

# ---- 2) board_r.c -------------------------------------------------------
p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

# 2a) RAM banks declaration + logging, right after the ABL tree lookup
old = '''		if (!memreg)
			memlen = 0;
		tb_logv("ABL MEM REGLEN", (ulong)memlen);'''
new = '''		if (!memreg)
			memlen = 0;
		tb_logv("ABL MEM REGLEN", (ulong)memlen);

		/* U-Boot parsed these out of SMEM (or the ABL tree) at board_init_f;
		 * they are what XBL considers usable RAM. */
		nb = qcom_get_ram_banks(rb_start, rb_size, 4);
		tb_logv("RAM BANKS", (ulong)nb);
		for (i = 0; i < nb && i < 2; i++) {
			tb_logv(i ? "BANK1 START" : "BANK0 START",
				(ulong)rb_start[i]);
			tb_logv(i ? "BANK1 SIZE" : "BANK0 SIZE",
				(ulong)rb_size[i]);
		}'''
assert s.count(old) == 1, ("banklog", s.count(old))
s = s.replace(old, new, 1)

old = '''		ulong rawdtb = kload + 0x3000000UL;	/* past the 44 MiB image */
		ulong kfdt = kload + 0x3800000UL;
		ulong srclen = 0;
		int rc;'''
new = '''		ulong rawdtb = kload + 0x3000000UL;	/* past the 44 MiB image */
		ulong kfdt = kload + 0x3800000UL;
		ulong srclen = 0;
		phys_addr_t rb_start[4];
		phys_size_t rb_size[4];
		int nb = 0, i;
		int rc;'''
assert s.count(old) == 1, ("decls", s.count(old))
s = s.replace(old, new, 1)

# 2b) /memory fallback: the SMEM banks, not a clipped span
old = '''				if (!nreg) {
					/* One bank from what U-Boot parsed,
					 * clipped so that it does not claim the
					 * firmware area below the line ABL's own
					 * placement implies. */
					u64 base = gd->ram_base;
					u64 size = gd->ram_size;

					if (base < 0xa0000000ULL) {
						size -= 0xa0000000ULL - base;
						base = 0xa0000000ULL;
					}
					mreg[0] = cpu_to_fdt64(base);
					mreg[1] = cpu_to_fdt64(size);
					nreg = 1;
				}'''
new = '''				if (!nreg) {
					int k;

					/* Nothing to copy: the banks U-Boot got out
					 * of SMEM. No clipping - their first start is
					 * already above the firmware carveouts. */
					for (k = 0; k < nb && k < 4; k++) {
						mreg[2 * k] =
							cpu_to_fdt64(rb_start[k]);
						mreg[2 * k + 1] =
							cpu_to_fdt64(rb_size[k]);
					}
					nreg = k;
				}'''
assert s.count(old) == 1, ("memfallback", s.count(old))
s = s.replace(old, new, 1)

# 2c) canary word for the new window
old = '''					if (!hit)
						hit = tb_ram_find("Linux version",
								  kload + srclen,
								  kload + img);
					tb_logv("PRV NEW HIT", hit);'''
new = '''					if (!hit)
						hit = tb_ram_find("Linux version",
								  kload + srclen,
								  kload + img);
					tb_logv("PRV NEW HIT", hit);
					/* 5a5a5a5a5a5a5a5a here next boot means
					 * head.S never cleared .bss. */
					tb_logv("PRV NEW W0",
						tb_ram_rd64(kload + srclen));'''
assert s.count(old) == 1, ("canarylog", s.count(old))
s = s.replace(old, new, 1)

# 2d) free the screen: DM block, failures only
old = '''		tb_screen_log("DM_INIT", 3);
		rc = dm_init(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		/* dm_scan() is internal; dm_scan_fdt() plus dm_scan_other() is what
		 * it does, and both are public. */
		tb_screen_log("DM_SCAN_FDT", 3);
		rc = dm_scan_fdt(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		tb_screen_log("DM_SCAN_OTHER", 3);
		rc = dm_scan_other(false);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		/* The autoprobe we no longer run used to provide the timer; U-Boot's
		 * delays and timeouts need one, so probe it explicitly. */
		{
			struct udevice *tv = NULL;

			rc = uclass_first_device_err(UCLASS_TIMER, &tv);
			tb_screen_log(rc ? "TIMER FAIL" : "TIMER OK", 3);
			tb_screen_log_hex((ulong)(unsigned int)rc, 3);
		}'''
new = '''		rc = dm_init(false);
		if (rc)
			tb_logv("DM INIT", (ulong)(unsigned int)rc);

		/* dm_scan() is internal; dm_scan_fdt() plus dm_scan_other() is what
		 * it does, and both are public. */
		rc = dm_scan_fdt(false);
		if (rc)
			tb_logv("DM SCAN FDT", (ulong)(unsigned int)rc);

		rc = dm_scan_other(false);
		if (rc)
			tb_logv("DM SCAN OTHER", (ulong)(unsigned int)rc);

		/* The autoprobe we no longer run used to provide the timer; U-Boot's
		 * delays and timeouts need one, so probe it explicitly. This build
		 * has no timer driver, so -EOPNOTSUPP is expected and not logged. */
		{
			struct udevice *tv = NULL;

			rc = uclass_first_device_err(UCLASS_TIMER, &tv);
			if (rc && rc != -EOPNOTSUPP)
				tb_logv("TIMER", (ulong)(unsigned int)rc);
		}'''
assert s.count(old) == 1, ("dmblock", s.count(old))
s = s.replace(old, new, 1)

# 2e) free the screen: UFS/SCSI, one line each
old = '''	tb_screen_log("PROBE UFS", 3);

	{
		struct udevice *uv = NULL;
		int rc = uclass_first_device_err(UCLASS_UFS, &uv);

		tb_screen_log(rc ? "UFS FAIL" : "UFS OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);
		if (uv)
			tb_screen_log(uv->name, 3);
	}

	tb_screen_log("SCSI SCAN", 3);

	{
		struct udevice *sv;
		int rc, n = 0;

		rc = scsi_scan(true);
		tb_screen_log(rc ? "SCSI FAIL" : "SCSI OK", 3);
		tb_screen_log_hex((ulong)(unsigned int)rc, 3);

		for (uclass_first_device(UCLASS_SCSI, &sv); sv;
		     uclass_next_device(&sv))
			n++;
		tb_screen_log("SCSI COUNT", 3);
		tb_screen_log_hex((ulong)n, 3);
	}'''
new = '''	{
		struct udevice *uv = NULL;
		int rc = uclass_first_device_err(UCLASS_UFS, &uv);

		tb_logv("UFS", (ulong)(unsigned int)rc);
	}

	{
		struct udevice *sv;
		int rc, n = 0;

		rc = scsi_scan(true);
		tb_logv("SCSI", (ulong)(unsigned int)rc);

		for (uclass_first_device(UCLASS_SCSI, &sv); sv;
		     uclass_next_device(&sv))
			n++;
		tb_logv("SCSI CNT", (ulong)n);
	}'''
assert s.count(old) == 1, ("ufsscsi", s.count(old))
s = s.replace(old, new, 1)

# 2f) declare the accessor
old = "int cleanup_before_linux(void);"
new = '''int cleanup_before_linux(void);
int qcom_get_ram_banks(phys_addr_t *start, phys_size_t *size, int max);'''
assert s.count(old) == 1, ("qcomdecl", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c/dram.c: SMEM banks for /memory, canary word logged, screen freed")
