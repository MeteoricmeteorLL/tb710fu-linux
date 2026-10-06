#!/usr/bin/env python3
f = '/home/meteor/u-boot-13r/dts/upstream/src/arm64/qcom/sm8650-lenovo-tb710fu.dts'
s = open(f).read()
old = '''	chosen {
		stdout-path = "serial0:115200n8";
		bootargs = "loglevel=8";
	};'''
new = '''	chosen {
		stdout-path = "serial0:115200n8,vidconsole";
		bootargs = "loglevel=8";
	};'''
if old not in s:
    raise SystemExit('anchor not found')
open(f, 'w').write(s.replace(old, new))
print('stdout-path now includes vidconsole')