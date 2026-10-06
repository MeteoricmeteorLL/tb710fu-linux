#!/usr/bin/env python3
"""Pack a U-Boot build into the ABL boot-image format the b slot takes.

The image is a 4 KiB boot-image header followed by a gzip of u-boot.bin, and the
header's kernel_size (offset 8, u32) is the payload length - the value ABL reads
to know how much of the kernel slot to decompress. Verified against
memboot12-boot_b.img, whose header field equalled its payload length exactly and
whose payload gunzipped back to the 1448968-byte u-boot.bin of that build.

Usage: pack_uboot_image.py <header-template.img> <u-boot.bin> <out.img>
"""
import gzip
import io
import struct
import sys

tmpl, uboot, out = sys.argv[1], sys.argv[2], sys.argv[3]

src = io.open(tmpl, "rb").read()
header = bytearray(src[:4096])
assert bytes(header[0:8]) == b"ANDROID!", "template is not a boot image"

raw = io.open(uboot, "rb").read()
buf = io.BytesIO()
with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
    gz.write(raw)
payload = buf.getvalue()

struct.pack_into("<I", header, 8, len(payload))

with io.open(out, "wb") as f:
    f.write(bytes(header))
    f.write(payload)

print("u-boot.bin   %d bytes" % len(raw))
print("gzip payload %d bytes" % len(payload))
print("wrote        %s (%d bytes)" % (out, 4096 + len(payload)))
