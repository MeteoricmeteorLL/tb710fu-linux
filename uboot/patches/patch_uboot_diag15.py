#!/usr/bin/env python3
"""TB710FU U-Boot build #15 - draw synchronous aborts on the screen.

The relocation fixup loop stalls at roughly the same table entry no matter what
changes: destination address differs between builds (0xffdc7000 vs 0xffdc8000),
layout and size differ, the pre-loop drawing cost differs by 27 MiB, and a full
power cycle changed nothing. That points at the table content at that entry, and
the most likely mechanism left is a synchronous abort on a table read or on a
guarded write.

This board has no console, so the ARM64 synchronous-abort handler gets a screen
dump instead: the faulting PC, FAR, ESR and the registers that identify the
entry (x2 = table pointer, x0/x1 = its fields). Those values let me find the
exact relocation locally. The dump persists across the watchdog reset because
nothing wipes the panel any more.
"""
import io

U = "/home/meteor/u-boot-13r/"
p = U + "arch/arm/lib/interrupts_64.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """void do_sync(struct pt_regs *pt_regs)
{
	if (CONFIG_IS_ENABLED(SEMIHOSTING_FALLBACK) &&
	    smh_emulate_trap(pt_regs))
		return;
	efi_restore_gd();
"""
new = """void do_sync(struct pt_regs *pt_regs)
{
	/*
	 * TB710FU: this board has no console, so draw the fault on the splash
	 * framebuffer, which the display pipeline still scans out. elr is the
	 * faulting PC, far the fault address, esr the syndrome, and for the
	 * relocation fixup loop x2 is the table pointer while x0/x1 are the
	 * entry fields. Nothing wipes the panel any more, so this survives the
	 * watchdog reset and can be photographed afterwards.
	 */
	{
		extern void tb_screen_log(const char *s, int scale);
		extern void tb_screen_log_hex(ulong v, int scale);
		unsigned long el, far = 0;

		asm("mrs	%0, CurrentEl" : "=r" (el));
		switch ((el >> 2) & 3) {
		case 1:
			asm("mrs	%0, FAR_EL1" : "=r" (far));
			break;
		case 2:
			asm("mrs	%0, FAR_EL2" : "=r" (far));
			break;
		}

		tb_screen_log("ABORT PC", 3);
		tb_screen_log_hex((ulong)pt_regs->elr, 3);
		tb_screen_log("ABORT FAR", 3);
		tb_screen_log_hex(far, 3);
		tb_screen_log("ABORT ESR", 3);
		tb_screen_log_hex((ulong)pt_regs->esr, 3);
		tb_screen_log("ABORT X2 TABLE", 3);
		tb_screen_log_hex((ulong)pt_regs->regs[2], 3);
		tb_screen_log("ABORT X0 ENTRY", 3);
		tb_screen_log_hex((ulong)pt_regs->regs[0], 3);
		tb_screen_log("ABORT X1 ENTRY", 3);
		tb_screen_log_hex((ulong)pt_regs->regs[1], 3);
	}

	if (CONFIG_IS_ENABLED(SEMIHOSTING_FALLBACK) &&
	    smh_emulate_trap(pt_regs))
		return;
	efi_restore_gd();
"""
assert s.count(old) == 1, ("do_sync anchor", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("interrupts_64.c: synchronous aborts now dumped to the screen")
