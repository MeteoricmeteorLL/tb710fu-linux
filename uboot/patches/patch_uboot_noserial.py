#!/usr/bin/env python3
# Fix U-Boot hang at serial_init: uart15 GENI clock is stubbed (CLK_STUB),
# unclocked register access hangs the bus. Disable serial, use vidconsole.
dts = '/home/meteor/u-boot-13r/dts/upstream/src/arm64/qcom/sm8650-lenovo-tb710fu.dts'
s = open(dts).read()

old = '''&uart15 {
	status = "okay";
};'''
new = '''/* uart15 disabled for bring-up: GCC QUP clock is stubbed (CONFIG_CLK_STUB),
 * touching the unclocked GENI SE hangs the bus inside serial_init(). */
&uart15 {
	status = "disabled";
};'''
assert old in s, 'uart15 override not found'
s = s.replace(old, new)

old2 = '''	chosen {
		stdout-path = "serial0:115200n8,vidconsole";
		bootargs = "loglevel=8";
	};'''
new2 = '''	chosen {
		stdout-path = "vidconsole";
		bootargs = "loglevel=8";
	};'''
assert old2 in s, 'chosen anchor not found'
s = s.replace(old2, new2)
open(dts, 'w').write(s)

cfg = '/home/meteor/u-boot-13r/configs/sm8650-lenovo-tb710fu_defconfig'
c = open(cfg).read()
if 'CONFIG_REQUIRE_SERIAL_CONSOLE' not in c:
    c += '\n# No physical UART on TB710FU bring-up; screen is the console\n# CONFIG_REQUIRE_SERIAL_CONSOLE is not set\n'
    open(cfg, 'w').write(c)
print('dts + defconfig patched: no serial, vidconsole console')