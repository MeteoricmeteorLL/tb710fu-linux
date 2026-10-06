#!/usr/bin/env python3
f = '/home/meteor/u-boot-13r/dts/upstream/src/arm64/qcom/sm8650-lenovo-tb710fu.dts'
s = open(f).read()

# Add a splash reserved region and a simple-framebuffer pointing at the ABL splash fb (0xD5100000).
old = '''	reserved-memory {
		ramoops@ac300000 {'''
new = '''	reserved-memory {
		/* Continuous splash framebuffer left by ABL/UEFI; keep it out of U-Boot's pool. */
		splash_region@d5100000 {
			no-map;
			reg = <0x0 0xd5100000 0x0 0x1000000>;
		};

		ramoops@ac300000 {'''
assert old in s, 'reserved-memory anchor not found'
s = s.replace(old, new)

# Framebuffer node for U-Boot's simple-fb console (VIDEO_SIMPLE).
old2 = '''	chosen {
		stdout-path = "serial0:115200n8";
		bootargs = "loglevel=8";
	};'''
new2 = '''	chosen {
		stdout-path = "serial0:115200n8";
		bootargs = "loglevel=8";
	};

	framebuffer@d5100000 {
		compatible = "simple-framebuffer";
		reg = <0x0 0xd5100000 0x0 0x100000>;
		width = <640>;
		height = <400>;
		stride = <2560>;
		format = "a8r8g8b8";
	};'''
assert old2 in s, 'chosen anchor not found'
s = s.replace(old2, new2)

open(f, 'w').write(s)
print('dts patched: added splash reserved-memory + simple-framebuffer')