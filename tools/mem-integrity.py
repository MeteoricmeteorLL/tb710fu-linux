#!/usr/bin/env python3
# TB710FU 运行时 RAM 完整性检测
#   分配 N MiB, 每 1MiB 块填充块序号 (8B 小端 x 131072), 然后反复校验并定位坏字节
# 用法: python3 mem-integrity.py <MiB> <秒> [标签]
import sys, struct, time, os

MB = int(sys.argv[1])
SECS = int(sys.argv[2])
LABEL = sys.argv[3] if len(sys.argv) > 3 else 'run'
CH = 1 << 20
N = CH // 8

buf = bytearray(MB * CH)
for i in range(MB):
    buf[i * CH:(i + 1) * CH] = struct.pack('<Q', i) * N
print('[%s] allocated+filled %d MiB (%d bytes)' % (LABEL, MB, MB * CH))
sys.stdout.flush()

t0 = time.time()
rnd = 0
total_bad = 0
while time.time() - t0 < SECS:
    rnd += 1
    bad = []
    for i in range(MB):
        exp = struct.pack('<Q', i)
        seg = buf[i * CH:(i + 1) * CH]
        if seg != exp * N:
            off = len(seg)
            for j in range(0, len(seg), 8):
                if seg[j:j + 8] != exp:
                    off = j
                    break
            bad.append((i, off, bytes(seg[off:off + 8]).hex()))
            if len(bad) >= 10:
                break
    total_bad += len(bad)
    print('[%s] round %d t=%.0fs bad=%d %s' % (LABEL, rnd, time.time() - t0, len(bad), bad[:10]))
    sys.stdout.flush()
    if len(bad) >= 10:
        break
    time.sleep(1)

print('[%s] DONE rounds=%d total_bad=%d' % (LABEL, rnd, total_bad))
os.system('dmesg | tail -8')
