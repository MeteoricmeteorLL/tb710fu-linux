#!/usr/bin/env python3
# TB710FU: 证明"页缓存被改坏而磁盘正确"
#   写 N MiB 带序号模式 -> fsync+sync -> 先在【页缓存】里扫描坏块并打印上下文文本
#   -> drop_caches -> 再从【磁盘】扫描, 应当 0 坏块
# 用法: python3 largefile-cache-corruption.py [MiB]
import os, sys, struct, hashlib

MB = int(sys.argv[1]) if len(sys.argv) > 1 else 3072
PATH = '/var/tmp/cc'
CH = 1 << 20
N = CH // 8
EXP = [struct.pack('<Q', i) * N for i in range(MB)]

print('== writing %d MiB to %s' % (MB, PATH)); sys.stdout.flush()
h = hashlib.md5()
with open(PATH, 'wb') as f:
    for i in range(MB):
        f.write(EXP[i]); h.update(EXP[i])
    f.flush(); os.fsync(f.fileno())
src = h.hexdigest()
print('md5_src   = %s' % src); sys.stdout.flush()

def scan(tag, ascii_ctx=False):
    bad = []
    with open(PATH, 'rb') as f:
        for i in range(MB):
            d = f.read(CH)
            if d != EXP[i]:
                e = struct.pack('<Q', i)
                off = next((j for j in range(0, len(d), 8) if d[j:j+8] != e), len(d))
                bad.append((i, off))
                if ascii_ctx and len(bad) <= 8:
                    lo = max(0, off - 32); hi = min(len(d), off + 96)
                    txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in d[lo:hi])
                    print('   BAD mib=%d byteoff=%d abs=%d' % (i, off, i * CH + off))
                    print('       before=%s' % ''.join(chr(c) if 32 <= c < 127 else '.' for c in d[max(0,off-64):off]))
                    print('       at    =%s' % txt)
                    print('       hex   =%s' % d[off:off+16].hex())
                if len(bad) >= 40:
                    break
    print('%s: bad_chunks=%d %s' % (tag, len(bad), bad[:12]))
    return len(bad)

os.system('sync')
n1 = scan('SCAN-CACHE(no drop)', ascii_ctx=True)

h = hashlib.md5()
with open(PATH, 'rb') as f:
    while True:
        d = f.read(CH * 8)
        if not d: break
        h.update(d)
print('md5_cache = %s  %s' % (h.hexdigest(), 'MATCH' if h.hexdigest() == src else 'DIFFER'))
sys.stdout.flush()

os.system('echo 3 > /proc/sys/vm/drop_caches')
os.system('sync')
n2 = scan('SCAN-DISK (after drop)')
print('== VERDICT: cache_bad=%d disk_bad=%d -> %s' %
      (n1, n2, 'CACHE-ONLY CORRUPTION (RAM overwritten)' if (n1 and not n2) else ('OK' if not n1 and not n2 else 'disk problem')))
os.remove(PATH)
