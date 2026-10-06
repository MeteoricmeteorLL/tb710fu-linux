#!/usr/bin/env python3
"""Build #40 (memboot12): prove the hand-off with a 104-byte stub.

If the zeroed .bss still leaves PRV BOOT ARGS at zero, then the kernel does not
execute even its first few instructions, and the question becomes whether the
hand-off itself works: does code run at kload, is x0 the device tree pointer,
which exception level is the CPU at, and is the MMU/cache state what a kernel
expects. Nothing in the kernel can answer that, so measure it directly.

The stub (mainline-kernel/stub-handoff.S, assembled to the bytes below) stores
x0, CurrentEL, SCTLR and MIDR at 0x8F000000 - plain DRAM, below the firmware
carveouts, outside everything this boot touches - writes a magic last, and
spins. U-Boot jumps to it through the same cleanup_before_linux() plus
armv8_switch_to_el2() path the kernel gets.

Behaviour: if the magic is absent the stub has not run yet, so copy it to
0x8F008000 and jump there (the run that produces the record). If it is present,
print the record and carry on to the kernel, so one reset yields both the
hand-off verdict and a fresh kernel attempt.

Also invalidate the instruction cache before either jump: U-Boot runs with the
MMU and caches as the bootloader left them, and stale lines over a freshly
written image are exactly the kind of thing that makes new code execute as old.
"""
import io

STUB = bytes([
    0xc1, 0x02, 0x00, 0x58, 0x20, 0x00, 0x00, 0xf9, 0x42, 0x42, 0x38, 0xd5,
    0x42, 0xfc, 0x42, 0xd3, 0x22, 0x04, 0x00, 0xf9, 0x5f, 0x0c, 0x00, 0xf1,
    0xe0, 0x00, 0x00, 0x54, 0x5f, 0x08, 0x00, 0xf1, 0x60, 0x00, 0x00, 0x54,
    0x03, 0x10, 0x38, 0xd5, 0x04, 0x00, 0x00, 0x14, 0x03, 0x10, 0x3c, 0xd5,
    0x02, 0x00, 0x00, 0x14, 0x03, 0x10, 0x3e, 0xd5, 0x23, 0x08, 0x00, 0xf9,
    0x04, 0x00, 0x38, 0xd5, 0x24, 0x0c, 0x00, 0xf9, 0xe5, 0x00, 0x00, 0x58,
    0x25, 0x10, 0x00, 0xf9, 0x5f, 0x20, 0x03, 0xd5, 0xff, 0xff, 0xff, 0x17,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x8f, 0x00, 0x00, 0x00, 0x00,
    0xde, 0xc0, 0x11, 0x5a, 0x00, 0x00, 0x00, 0x00,
])
stub_c = ",\n\t".join(", ".join("0x%02x" % b for b in STUB[i:i + 12])
                      for i in range(0, len(STUB), 12))

p = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = "#define TB_K_KIMAGE_VOFFSET\t0x1f74000UL\t/* kimage_voffset */"
new = '''#define TB_K_KIMAGE_VOFFSET	0x1f74000UL	/* kimage_voffset */

/* Hand-off probe: scratch record and where to copy the stub. Plain DRAM below
 * the firmware carveouts, outside everything this boot reads or writes. */
#define TB_STUB_ADDR		0x8f008000UL
#define TB_STUB_SCRATCH		0x8f000000UL
#define TB_STUB_MAGIC		0x5a11c0deUL

/* Assembled from mainline-kernel/stub-handoff.S: store x0, CurrentEL, SCTLR and
 * MIDR at TB_STUB_SCRATCH, write the magic last, spin. */
static const unsigned char tb_stub[] = {
	%s
};''' % stub_c
assert s.count(old) == 1, ("defs", s.count(old))
s = s.replace(old, new, 1)

# read the record next to the other probes
old = '''					tb_logv("PRV BOOT ARGS", tb_ram_rd64(kload +'''
new = '''					tb_logv("STUB MAGIC", tb_ram_rd64(
							TB_STUB_SCRATCH + 32));
					tb_logv("STUB X0", tb_ram_rd64(
							TB_STUB_SCRATCH));
					tb_logv("STUB EL", tb_ram_rd64(
							TB_STUB_SCRATCH + 8));
					tb_logv("STUB SCTLR", tb_ram_rd64(
							TB_STUB_SCRATCH + 16));
					tb_logv("STUB MIDR", tb_ram_rd64(
							TB_STUB_SCRATCH + 24));
					tb_logv("PRV BOOT ARGS", tb_ram_rd64(kload +'''
assert s.count(old) == 1, ("probe", s.count(old))
s = s.replace(old, new, 1)

# the hand-off itself
old = '''			tb_screen_log("JUMP", 3);
			/* The hand-off bootm makes, without the command
			 * interpreter, the environment or the image machinery,
			 * none of which this board's bring-up sets up. */
			cleanup_before_linux();
			armv8_switch_to_el2((u64)kfdt, 0, 0, 0,
					    (u64)kload, ES_TO_AARCH64);'''
new = '''			{
				ulong entry = kload;

				/* First pass: run the probe instead of the
				 * kernel, so the next boot can report what the
				 * hand-off actually delivered. */
				if (tb_ram_rd64(TB_STUB_SCRATCH + 32) !=
				    TB_STUB_MAGIC) {
					memcpy((void *)TB_STUB_ADDR, tb_stub,
					       sizeof(tb_stub));
					entry = TB_STUB_ADDR;
					tb_screen_log("STUB RUN", 3);
				} else
					tb_screen_log("JUMP", 3);

				/* U-Boot runs with whatever cache state the
				 * bootloader left; stale instruction lines over
				 * either payload would run old code. */
				icache_disable();
				invalidate_icache_all();

				/* The hand-off bootm makes, without the command
				 * interpreter, the environment or the image
				 * machinery, none of which this board's bring-up
				 * sets up. */
				cleanup_before_linux();
				armv8_switch_to_el2((u64)kfdt, 0, 0, 0,
						    (u64)entry, ES_TO_AARCH64);
			}'''
assert s.count(old) == 1, ("jump", s.count(old))
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: hand-off stub embedded, record readout added")
