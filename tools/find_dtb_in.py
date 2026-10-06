"""Find device trees embedded in an image and show markers that identify them.

String-searching a whole bootloader image is misleading: U-Boot's own DWC3
driver contains the literal "qcom,select-utmi-as-pipe-clk", so its presence says
nothing about the DTB.  This walks the 0xd00dfeed blobs instead, takes each
blob's declared size, and reports what only a device tree can show:

  model  - our board DTS says "Lenovo Xiaoxin Pad Pro GT (TB710FU)"; the vendor
           tree and the dtbo files say "... GT,TB710FU" with a comma
  utmi   - qcom,select-utmi-as-pipe-clk on usb_1 (the fix that made DWC3 init)
  keep   - the provisional tb-icc-keepalive node
  fb     - the framebuffer reservation at 0xd5100000
  ufs    - whether ufshc is switched on

Usage: find_dtb_in.py <file> [file...]
"""

import io
import struct
import sys

MAGIC = b"\xd0\x0d\xfe\xed"


def blobs(data):
    off = 0
    while True:
        i = data.find(MAGIC, off)
        if i < 0:
            return
        off = i + 4
        if i + 8 > len(data):
            return
        size = struct.unpack_from(">I", data, i + 4)[0]
        if size < 100 or i + size > len(data):
            continue
        yield i, data[i:i + size]


def main():
    for path in sys.argv[1:]:
        data = io.open(path, "rb").read()
        found = False
        for off, blob in blobs(data):
            found = True
            # model strings, crude but effective: printable runs after "model"
            models = []
            for key in (b"Lenovo Xiaoxin Pad Pro GT (TB710FU)",
                        b"Lenovo Xiaoxin Pad Pro GT,TB710FU",
                        b"Lenovo Xiaoxin Pad Pro GT"):
                if key in blob:
                    models.append(key.decode())
            print("%-40s dtb@0x%-9x size=%-7d utmi=%-5s keep=%-5s fb=%-5s ufs=%-5s model=%s" % (
                path.replace("mainline-kernel\\", "").replace("mainline-kernel/", ""),
                off, len(blob),
                b"select-utmi-as-pipe-clk" in blob,
                b"tb-icc-keepalive" in blob,
                b"d5100000" in blob,
                b"ufshc@1d84000" in blob and b"okay" in blob,
                "; ".join(models) or "-"))
        if not found:
            print("%-40s (no device tree blob)" % path)


main()
