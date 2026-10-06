#!/usr/bin/env python3
"""acm32 init 补丁：linsys 真 ext4 根直挂（2026-10-05 重分区配套）。

在 /tmp/acm32/init（acm31 提取件）上做 7 处编辑，旧 squashfs+overlay 链全部保留为兜底：

  1. mkdir 锚点后插入 linsys 直挂块：挂 linsys ext4 -> 有 os-release 则挂 linboot 到
     /boot、写 resolv.conf、touch /ovl/.ready（REALROOT=yes）；空盘则 umount 回退。
  2. /rootfs 等待循环加 REALROOT 门（直挂成功不再白等 60s）。
  3. 旧 overlay 块入口加 REALROOT 门（防双挂 /ovl/mnt）。
  4. UDEV 兜底去掉 userdata（userdata 现在是安卓分区，绝不能被 loop7+mke2fs 摸）。
  5. RFS 兜底同样去掉 userdata。
  6. handoff 的 busybox cp 改条件式（ext4 根不清真根的 /bin/busybox，缺了才补）。
  7. klogd.sh 落点分流：overlay 旧路径仍写 /ovlhost/up；直挂 ext4 根写进 /ovl/mnt。

幂等：以 'linsys' 已存在为标志跳过。
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else "/tmp/acm32/init"
s = io.open(P, encoding="utf-8", errors="surrogateescape").read()

if "find_part linsys" in s:
    print("already patched (linsys present) - nothing to do")
    raise SystemExit(0)

BLOCK = """\t\t# --- acm32: linsys = real ext4 root (2026-10-05 repartition) ---
\t\t# New layout: linsys(sda15) is the real ext4 root, linboot(sda14) mounts at
\t\t# /boot. Mount directly when it holds a full system; an empty linsys (fresh
\t\t# deployment) umounts and falls through to the old squashfs+overlay path.
\t\tREALROOT=
\t\tLSYS=$(find_part linsys)
\t\tif [ -b "$LSYS" ] && mount -t ext4 -o rw "$LSYS" /ovl/mnt 2>/dev/null; then
\t\t\tif [ -e /ovl/mnt/etc/os-release ]; then
\t\t\t\tREALROOT=yes
\t\t\t\t[ -d /ovl/mnt/boot ] || mkdir -p /ovl/mnt/boot
\t\t\t\tBP=$(find_part linboot)
\t\t\t\t[ -b "$BP" ] && mount -t ext4 "$BP" /ovl/mnt/boot 2>/dev/null
\t\t\t\techo "nameserver 223.5.5.5" > /ovl/mnt/etc/resolv.conf
\t\t\t\ttouch /ovl/.ready
\t\t\t\tkmsg "finalize: REAL ext4 root on $LSYS (boot=$BP)"
\t\t\telse
\t\t\t\tumount /ovl/mnt 2>/dev/null
\t\t\t\tkmsg "finalize: linsys has no os-release - falling back"
\t\t\tfi
\t\tfi
"""


def sub1(pat, rep, name, count=1):
    global s
    new, n = re.subn(pat, rep, s, count=count)
    assert n == count, f"EDIT FAILED: {name} (matches={n}, want {count})"
    s = new
    print(f"ok: {name}")


# 1) 插入 linsys 直挂块（mkdir 锚点后）
sub1(r"(mkdir -p /ovl/up /ovl/work /ovl/mnt /ovlhost\n)",
     r"\1" + BLOCK,
     "insert linsys block")

# 2) /rootfs 等待循环加门
sub1(r"while \[ \$i -lt 60 \] && \[ ! -e /rootfs/bin/sh \]",
     'while [ $i -lt 60 ] && [ -z "$REALROOT" ] && [ ! -e /rootfs/bin/sh ]',
     "gate /rootfs wait loop")

# 3) 旧 overlay 块入口加门
sub1(r"if \[ -e /rootfs/bin/sh \]; then",
     'if [ -z "$REALROOT" ] && [ -e /rootfs/bin/sh ]; then',
     "gate overlay block")

# 4) UDEV 兜底去 userdata
sub1(r"UDEV=\$\(find_part linroot\) \|\| UDEV=\$\(find_part userdata\) \|\| UDEV=",
     "UDEV=$(find_part linroot) || UDEV=",
     "UDEV: drop userdata fallback")

# 5) RFS 兜底去 userdata
sub1(r"RFS=\$\(find_part linroot\) \|\| RFS=\$\(find_part userdata\) \|\| RFS=",
     "RFS=$(find_part linroot) || RFS=",
     "RFS: drop userdata fallback")

# 6) busybox cp 条件式
sub1(r"(\t)cp /bin/busybox /ovl/mnt/bin/busybox 2>/dev/null\n",
     r"\1[ -d /ovlhost/up ] && cp /bin/busybox /ovl/mnt/bin/busybox 2>/dev/null\n"
     r"\1[ -e /ovl/mnt/bin/busybox ] || cp /bin/busybox /ovl/mnt/bin/busybox 2>/dev/null\n",
     "busybox cp conditional")

# 7) klogd 落点分流（printf 单行太长，用逐行精确替换）
old7 = ("\tprintf '#!/bin/busybox sh\\nwhile :; do /bin/busybox sh -c \"/bin/busybox dmesg | "
        "/bin/busybox tail -c 200000 > /dev/sda13\" 2>/dev/null; /bin/busybox sleep 2; done\\n' "
        "> /ovlhost/up/klogd.sh\n"
        "\tchmod +x /ovlhost/up/klogd.sh\n"
        "\t/ovlhost/up/klogd.sh &\n")
new7 = ("\tif [ -d /ovlhost/up ]; then KD=/ovlhost/up; else KD=/ovl/mnt; fi\n"
        "\tprintf '#!/bin/busybox sh\\nwhile :; do /bin/busybox sh -c \"/bin/busybox dmesg | "
        "/bin/busybox tail -c 200000 > /dev/sda13\" 2>/dev/null; /bin/busybox sleep 2; done\\n' "
        "> $KD/klogd.sh\n"
        "\tchmod +x $KD/klogd.sh\n"
        "\t$KD/klogd.sh &\n")
assert old7 in s, "EDIT FAILED: klogd block (exact text not found)"
s = s.replace(old7, new7, 1)
print("ok: klogd reroute")

io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("init: acm32 linsys patch 完成")
