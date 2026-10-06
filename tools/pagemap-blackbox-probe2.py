#!/usr/bin/env python3
# TB710FU: 抓住运行时内存破坏者 —— 打印坏页的物理地址与内容
# 用法: python3 bbprobe2.py [MiB] [轮数] [间隔秒]
import ctypes, os, struct, sys, time

MB = int(sys.argv[1]) if len(sys.argv) > 1 else 3072
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 5
CH = 1 << 20
PAGE = 4096
SIZE = MB * CH
SLOTS = [0xB0000000, 0xD6A00000]

libc = ctypes.CDLL("libc.so.6", use_errno=True)
libc.mmap.restype = ctypes.c_void_p
libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, ctypes.c_long]
libc.memcpy.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
libc.memcmp.restype = ctypes.c_int
libc.memcmp.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]

addr = libc.mmap(None, SIZE, 1 | 2, 0x02 | 0x20, -1, 0)
print("mmap 0x%x size=%d MiB" % (addr, MB)); sys.stdout.flush()
def pat(i):
    return struct.pack('<Q', i) * (CH // 8)

for i in range(MB):
    libc.memcpy(ctypes.c_void_p(addr + i * CH), pat(i), CH)

fd = os.open('/proc/self/pagemap', os.O_RDONLY)
def pa_of(off):
    d = os.pread(fd, 8, ((addr + off) // PAGE) * 8)
    if len(d) < 8:
        return None
    e = struct.unpack('<Q', d)[0]
    if not (e >> 63):
        return None
    return (e & ((1 << 55) - 1)) << 12

def text(off, n=4096):
    b = ctypes.string_at(addr + off, n)
    return ''.join(chr(c) if 32 <= c < 127 else '.' for c in b)

seen = set()
for rnd in range(ROUNDS):
    found = []
    for i in range(MB):
        p = pat(i)
        if libc.memcmp(ctypes.c_void_p(addr + i * CH), p, CH):
            seg = ctypes.string_at(addr + i * CH, CH)
            e = p[:8]
            off = next((j for j in range(0, len(seg), 8) if seg[j:j + 8] != e), -1)
            found.append((i, off))
    new = [f for f in found if f not in seen]
    print("round %d: bad_blocks=%d new=%d %s" % (rnd, len(found), len(new), found[:8]))
    for (i, off) in new:
        seen.add((i, off))
        abs_off = i * CH + off
        page_off = abs_off & ~(PAGE - 1)
        pa = pa_of(page_off)
        near = ''
        if pa:
            for s in SLOTS:
                if s <= pa < s + 0x100000:
                    near = '  <<< IN SLOT %s +0x%x' % (hex(s), pa - s)
                elif abs(pa - s) < 0x200000:
                    near = '  (near slot %s, delta 0x%x)' % (hex(s), pa - s)
        print("  BAD block=%d off_in_block=%d page_off=%d pa=%s%s" %
              (i, off, page_off, hex(pa) if pa else None, near))
        print("    bytes=%s" % ctypes.string_at(addr + abs_off, 32).hex())
        print("    text =%s" % text(page_off + 0x300, 640))
    sys.stdout.flush()
    time.sleep(GAP)
os.close(fd)
