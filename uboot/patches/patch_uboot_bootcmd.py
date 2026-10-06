#!/usr/bin/env python3
f = '/home/meteor/u-boot-13r/board/qualcomm/default.env'
s = open(f).read()
old = 'bootcmd=run fastboot'
new = 'bootcmd=echo TB710FU_UBOOT_ALIVE'
assert old in s, 'bootcmd anchor not found'
s = s.replace(old, new)
open(f, 'w').write(s)
print('default.env bootcmd -> diagnostic echo (no auto fastboot)')