#!/usr/bin/env python3
"""TB710FU U-Boot: memboot 引导源从 recovery_a/b 切到新 linboot 分区 (2026-10-05)。

背景：sda 重划为 linboot(1GiB)/linsys(128GiB)/userdata(85.71GiB)；recovery_a 已被
TWRP 覆盖（DTB 头没了），recovery_b 保留 fix3 作为回退。memboot 从此全部读 linboot：

    linboot (sda14) 布局：
      0x0000000  Image.gz（补零到 16 MiB）          <- 0x1000 块
      0x1000000  TBIRD 头 + initramfs（2 MiB 窗口）  <- +0x1000 起 0x800 块
      0x1800000  DTB（补零到 0x22000）              <- +0x1800 起 0x22 块

改动（common/board_r.c，5 处）：
  1. 内核/initramfs 分区名 "recovery_b" -> "linboot"
  2. DTB 分区名 "recovery_a" -> "linboot"
  3. DTB 读偏移 dinfo.start -> dinfo.start + 0x1800
  4/5. 两处注释同步更新

幂等：已打过（含 "linboot"）则跳过对应编辑。
"""
import io
import re

P = "/home/meteor/u-boot-13r/common/board_r.c"
s = io.open(P, encoding="utf-8", errors="surrogateescape").read()


def sub1(pat, rep, name, required=True):
    global s
    new, n = re.subn(pat, rep, s, count=1)
    if n != 1:
        if not required:
            print(f"skip: {name}")
            return
        raise SystemExit(f"EDIT FAILED: {name} (matches={n})")
    s = new
    print(f"ok: {name}")


# 1) 内核+initramfs 分区名
sub1(r'"recovery_b"\)\) \{', '"linboot")) {', "kernel/initrd partname")

# 2) DTB 分区名
sub1(r'"recovery_a"\)\) \{', '"linboot")) {', "dtb partname")

# 3) DTB 读偏移与窗口：linboot 内 0x1800000 = 0x1800 个 4K 块；
#    散热补丁后紧凑树 146,062B，读窗口定 0x28 块 = 163,840B。
#    兼容两种基线：新基线是 0x22 块读（0x22000 头），tar(9/28) 基线是旧 0x1000 块大读取。
_n = len(re.findall(r"blk_dread\(ddesc, dinfo\.start \+ 0x1800, 0x28,", s))
if _n == 1:
    print("ok: dtb read already patched (0x1800/0x28 present)")
else:
    m22 = re.search(r"blk_dread\(ddesc, dinfo\.start, 0x22,", s)
    m_old = re.search(r"blk_dread\(ddesc, dinfo\.start, 0x1000,", s)
    if m22:
        s = s[:m22.start()] + "blk_dread(ddesc, dinfo.start + 0x1800, 0x28," + s[m22.end():]
        print("ok: dtb read offset +0x1800, window 0x28 (from 0x22 base)")
    elif m_old:
        old_blk = ("blk_dread(ddesc, dinfo.start, 0x1000,\n"
                   "\t\t\t\t\t\t(void *)rawdtb);\n"
                   "\t\t\t\tif (brc != 0x1000)")
        new_blk = ("/* TB710FU: DTB lives at linboot+0x1800 blocks (24 MiB);\n"
                   "\t\t\t\t * window 0x28 blocks = 160 KiB (thermal tree 146 KB).\n"
                   "\t\t\t\t */\n"
                   "\t\t\t\tbrc = blk_dread(ddesc, dinfo.start + 0x1800, 0x28,\n"
                   "\t\t\t\t\t\t(void *)rawdtb);\n"
                   "\t\t\t\tif (brc != 0x28)")
        n = s.count(old_blk)
        assert n == 1, f"tar-era dtb read anchor count={n}"
        s = s.replace(old_blk, new_blk)
        print("ok: dtb read offset +0x1800, window 0x28 (from tar 0x1000 base)")
    else:
        raise SystemExit("EDIT FAILED: dtb read anchor not found in either variant")

# 4) 注释：initramfs 位置说明
sub1(r"where the initramfs lives inside recovery_b",
     "where the initramfs lives inside linboot",
     "comment: initrd location", required=False)

# 5) 注释：DTB 树位置说明
sub1(r"the\s+tree in recovery_a carries",
     "the tree in linboot carries",
     "comment: dtb location", required=False)

io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c: memboot 引导源 -> linboot 完成")
