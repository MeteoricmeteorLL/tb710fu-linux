#!/usr/bin/env python3
"""TB710FU: 修 DTB —— 正确保留开机动画 framebuffer 与黑匣子槽位。

背景（已实测定位的静默内存损坏根因）
------------------------------------
linux 里有一套自绘的启动调试设施，用固定物理地址 __va(0xd5100000) 画东西
（引导梯子色块 tb_mark、tbfb 面板控制台、每 10s 一次的心跳仪 tb_gauge_draw、
initcall 进度条、黑匣子底部状态带），另外黑匣子的日志环写在 0xB0000000 与
0xD6A00000 各 1MiB（init/main.c 的 tb_bb_pa[]）。

这段 0xD5100000 起 25MiB 是 bootloader 的开机动画 framebuffer。U-Boot 每次启动
会自己往 /reserved-memory 加一个节点（common/board_r.c），但那行代码有两个 bug：

    u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };
    fdt_setprop(fdt, fn, "reg", reg, sizeof(reg));   /* ① */
    fdt_setprop_empty(fdt, fn, "no-map");            /* ② */

① fdt_setprop() 把小端主机内存里的 u32 数组原样拷进大端 DTB，每个 cell 字节反序：
   0xd5100000 -> 0x000010d5，0x01900000 -> 0x00009001。内核忠实地只去保留
   0x10d5 处 36865 字节（根本不是 RAM），真正那 25MiB 一个字节都没保留。
   内核日志里那句荒唐的 "framebuffer at 0x1045, 0x9001 bytes" 就是它。
② no-map 会把该区从内核线性映射里剔除；一旦 ① 修好，__va(0xd5100000) 立刻
   翻译失败（这正是当初那个 3.019s 崩溃的形状）。

后果：这 25MiB + 黑匣子 2MiB 被页分配器当普通 System RAM 发放
（/proc/iomem 里就是 "d5100000-d7bfffff : System RAM"），分配进去的页缓存/匿名页
随后被绘制代码反复改写 —— 表现为大文件（>2GiB，此时分配器才会回落到低地址段）
静默损坏：读页缓存得到的 md5 与磁盘不一致，而磁盘内容其实是对的。

修法
----
本工具在 **现有 DTB 上** 做外科手术（不重编内核树 DTS —— 树里的 DTS 是重建版，
与实机 DTB 内容不同，重编会丢东西）：

  1. 把 /reserved-memory/framebuffer@d5100000 的 reg 改成
     <0x00 0xd5100000 0x00 0x1900000>，并去掉它的 no-map；
  2. 补两个节点 tb-blackbox-a@b0000000 / tb-blackbox-b@d6a00000，各 1MiB。

三个区间都必须 **不带 no-map**：驱动要用 __va() 直接访问，必须在线性映射里。

U-Boot 那边只在节点"不存在"时才添加（fdt_add_subnode 失败就什么都不做），
所以这里声明/修正后它就动不了我们。

用法: fix-dtb-fb-reserve.py <输入.dtb> <输出.dtb>
"""
import re
import subprocess
import sys

FB_BASE, FB_SIZE = 0xd5100000, 0x1900000
BB = [(0xb0000000, 0x100000), (0xd6a00000, 0x100000)]
DTB_WINDOW = 0x28 * 4096          # U-Boot 读窗口 160 KiB

src = sys.argv[1] if len(sys.argv) > 1 else 'dtb-deployed-linboot.bin'
dst = sys.argv[2] if len(sys.argv) > 2 else 'dtb-fb-fixed.bin'


def dc(args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('dtc failed: %s' % r.stderr[-500:])
    return r.stdout


dts = dc(['dtc', '-I', 'dtb', '-O', 'dts', src])
lines = dts.split('\n')


def node_block(lines, header_re):
    """返回 (start, end, header_index): 节点行到下一条 '};' 闭括号的区间。"""
    for i, ln in enumerate(lines):
        if re.search(header_re, ln) and ln.rstrip().endswith('{'):
            depth = 0
            for j in range(i, len(lines)):
                depth += lines[j].count('{') - lines[j].count('}')
                if depth == 0:
                    return i, j
            break
    raise SystemExit('node not found: %s' % header_re)


# --- 1. 修正 framebuffer 节点（或新建）---
changed = []
try:
    i, j = node_block(lines, r'^\s*framebuffer@d5100000\s*\{')
    ind = re.match(r'(\s*)', lines[i]).group(1) + '\t'
    body = []
    for k in range(i + 1, j):
        t = lines[k]
        if re.match(r'^\s*no-map;\s*$', t):
            changed.append('framebuffer: dropped no-map')
            continue
        if re.match(r'^\s*reg\s*=', t):
            t = '%sreg = <0x00 0x%x 0x00 0x%x>;' % (ind, FB_BASE, FB_SIZE)
            changed.append('framebuffer: reg -> 0x%x/0x%x' % (FB_BASE, FB_SIZE))
        body.append(t)
    lines[i + 1:j] = body
except SystemExit:
    i, j = node_block(lines, r'^\s*reserved-memory\s*\{')
    ind = re.match(r'(\s*)', lines[i]).group(1) + '\t'
    lines[j:j] = ['%sframebuffer@d5100000 {' % ind,
                  '%s\treg = <0x00 0x%x 0x00 0x%x>;' % (ind, FB_BASE, FB_SIZE),
                  '%s};' % ind, '']
    changed.append('framebuffer: node created')

# --- 2. 黑匣子槽位 ---
for base, size in BB:
    name = 'tb-blackbox-%s@%x' % ('a' if base >> 28 < 0xd else 'b', base)
    if re.search(r'^\s*%s\s*\{' % re.escape(name), '\n'.join(lines)):
        continue
    i, j = node_block(lines, r'^\s*reserved-memory\s*\{')
    ind = re.match(r'(\s*)', lines[i]).group(1) + '\t'
    lines[j:j] = ['%s%s {' % (ind, name),
                  '%s\treg = <0x00 0x%x 0x00 0x%x>;' % (ind, base, size),
                  '%s};' % ind, '']
    changed.append('added %s 0x%x/0x%x' % (name, base, size))

out = '\n'.join(lines)
open('/tmp/_fixed.dts', 'w').write(out)
dc(['dtc', '-I', 'dts', '-O', 'dtb', '/tmp/_fixed.dts', '-o', dst])

hdr = open(dst, 'rb').read(8)
import struct
total = struct.unpack('>I', hdr[4:8])[0]
print('changes:')
for c in changed:
    print('  - %s' % c)
print('output: %s  totalsize=%d  window=%d  %s' %
      (dst, total, DTB_WINDOW, 'FITS' if total <= DTB_WINDOW else 'TOO BIG!'))
