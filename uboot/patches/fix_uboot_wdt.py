import io

p = "/home/meteor/u-boot-13r/common/board_f.c"
s = io.open(p, encoding="utf-8", errors="surrogateescape").read()

old = """
	/* TB710FU: XBL leaves the APPS watchdog armed and nothing in U-Boot
	 * feeds it, so this session is killed after a few tens of seconds.
	 * Clear the enable bit; the two layouts below cover the variants seen on
	 * these SoCs (plain and the one needing the 0x51F15E key). */
	{
		void *wdt = (void *)0x17C10000UL;

		writel(0x51F15E, wdt + 0x8);	/* secure kdog: disarm key */
		writel(0, wdt + 0x8);		/* WDT_EN */
		writel(0, wdt + 0x4);		/* WDT_RST */
	}"""
new = """
	/* TB710FU: do NOT touch 0x17C10000 here. Writing that watchdog block
	 * from board_init_f hangs the boot (the block is either unclocked or
	 * XPU-protected - same failure mode as uart15), which cost a build: the
	 * screen showed only the banner and the F sequence never finished. The
	 * watchdog stays armed and resets the board after some tens of seconds;
	 * U-Boot's work has to fit in that window. */
"""
assert s.count(old) == 1, ("wdt block", s.count(old))
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_f.c: hanging watchdog write removed")
