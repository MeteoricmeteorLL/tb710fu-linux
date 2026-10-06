#!/usr/bin/env python3
f = '/home/meteor/u-boot-13r/arch/arm/mach-snapdragon/board.c'
s = open(f).read()

new = '''	/* TB710FU bring-up: our internal DT carries mainline-style USB/display wiring.
	 * Memory is still parsed from the ABL external DT above, so RAM layout is correct.
	 */
	debug("TB710FU_USING_INTERNAL_FDT external=%d\\n", external_valid);
	(void)external_fdt;
	*fdtp = internal_fdt;
	ret = 0;'''

old = '''	if (external_valid) {
		debug("Using external ABL FDT\\n");
		*fdtp = external_fdt;
		ret = 0;
	} else {
		debug("Using built in FDT\\n");
		ret = -EEXIST;
	}'''

assert new in s, 'patched block not found (already reverted?)'
s = s.replace(new, old)
open(f, 'w').write(s)
print('board.c reverted to external-ABL-DT baseline')