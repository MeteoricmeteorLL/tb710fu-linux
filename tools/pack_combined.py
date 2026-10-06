"""Assemble the image that goes into recovery_b.

U-Boot loads this region and pulls two things out of it: the kernel Image.gz at
offset 0, and the initramfs at 0x1000000.  Layout:

    0x0000000  Image.gz
    ...        zero pad to 16 MiB
    0x1000000  16-byte header: "TBIRD" magic, u32 initramfs length, u32 rsvd
    0x1000010  initramfs.cpio.gz
    ...        zero pad to 18 MiB

The header exists because U-Boot used to carry this length as a hardcoded
constant, and rebuilding the ramdisk a few hundred bytes larger silently
truncated it -- the kernel then died with "Attempted to kill init" and nothing
else to go on.  Scanning backwards for the last non-zero byte does not work
either: the gzip trailer ends with the high byte of ISIZE, which is zero for any
initramfs under 16 MiB.

The file is padded to 18 MiB, i.e. the whole 2 MiB window U-Boot reads out of
recovery_b, so whatever the partition held before can never be mistaken for part
of the image.

Usage: pack_combined.py <Image.gz> <initramfs.cpio.gz> <out.img>
"""

import io
import struct
import sys

PAD = 0x1000000          # where the initramfs header starts
IR_HDR = 16              # magic[8] + len u32 + reserved u32
WINDOW = 0x200000        # 2 MiB that U-Boot reads out of recovery_b
MAGIC = b"TBIRD\0\0\0"

kern_path, init_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

kern = io.open(kern_path, "rb").read()
init = io.open(init_path, "rb").read()

if kern[:2] != b"\x1f\x8b":
    sys.exit("kernel payload does not look gzipped")
if init[:2] != b"\x1f\x8b":
    sys.exit("initramfs does not look gzipped")
if len(kern) > PAD - IR_HDR:
    sys.exit("kernel is %d bytes, does not fit before the %d-byte mark" % (len(kern), PAD))
if IR_HDR + len(init) > WINDOW:
    sys.exit("initramfs is %d bytes, does not fit in the %d-byte window" % (len(init), WINDOW))

head = MAGIC + struct.pack("<II", len(init), 0)
used = PAD + IR_HDR + len(init)

with io.open(out_path, "wb") as f:
    f.write(kern)
    f.write(b"\0" * (PAD - len(kern)))
    f.write(head)
    f.write(init)
    f.write(b"\0" * (PAD + WINDOW - used))

print("kernel    %9d bytes" % len(kern))
print("pad       %9d bytes" % (PAD - len(kern)))
print("initramfs %9d bytes at 0x%x (+%d header)" % (len(init), PAD + IR_HDR, IR_HDR))
print("zerofill  %9d bytes" % (PAD + WINDOW - used))
print("wrote     %s (%d bytes)" % (out_path, PAD + WINDOW))
