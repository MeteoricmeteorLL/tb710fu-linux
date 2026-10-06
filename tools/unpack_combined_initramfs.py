"""Unpack the initramfs out of a combined image, without needing cpio.

The combined image is what U-Boot loads out of recovery_b: Image.gz at offset 0,
a "TBIRD" header at 16 MiB carrying the initramfs length, then the gzipped cpio.
Answering "is the init I think I flashed actually in the image?" should not
depend on a cpio binary being installed, so the newc format is walked here.

Usage: unpack_combined_initramfs.py <combined.img> <outdir> [grep-substring]
"""

import gzip
import io
import os
import struct
import sys

MAGIC = b"TBIRD\0\0\0"
OFF = 0x1000000
HDR = 16


def walk(buf):
    off = 0
    while off + 110 <= len(buf):
        if buf[off:off + 6] not in (b"070701", b"070702"):
            return
        h = buf[off:off + 110]
        f = [int(h[6 + i * 8:6 + (i + 1) * 8], 16) for i in range(13)]
        mode, filesize, namesize = f[1], f[6], f[11]
        name = buf[off + 110:off + 110 + namesize - 1].decode("utf-8", "replace")
        data = off + 110 + namesize
        data = (data + 3) & ~3
        yield name, mode, buf[data:data + filesize]
        if name == "TRAILER!!!":
            return
        off = (data + filesize + 3) & ~3


def main():
    img_path, outdir = sys.argv[1], sys.argv[2]
    needle = sys.argv[3] if len(sys.argv) > 3 else None
    img = io.open(img_path, "rb").read()

    if img[OFF:OFF + 8] != MAGIC:
        sys.exit("no TBIRD header at 0x%x (got %r)" % (OFF, img[OFF:OFF + 8]))
    ln = struct.unpack("<I", img[OFF + 8:OFF + 12])[0]
    blob = img[OFF + HDR:OFF + HDR + ln]
    raw = gzip.decompress(blob)
    print("initramfs %d bytes gzipped, %d bytes unpacked" % (len(blob), len(raw)))

    os.makedirs(outdir, exist_ok=True)
    hits = 0
    for name, mode, data in walk(raw):
        if name in (".", "TRAILER!!!"):
            continue
        path = os.path.join(outdir, name)
        if mode & 0o170000 == 0o040000:
            os.makedirs(path, exist_ok=True)
            continue
        if mode & 0o170000 == 0o120000:
            print("symlink %s -> %s" % (name, data.decode("utf-8", "replace")))
            continue
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with io.open(path, "wb") as f:
            f.write(data)
        if needle:
            text = data.decode("utf-8", "replace")
            for i, line in enumerate(text.splitlines(), 1):
                if needle in line:
                    print("%s:%d: %s" % (name, i, line))
                    hits += 1
    if needle:
        print("%d line(s) containing %r" % (hits, needle))


main()
