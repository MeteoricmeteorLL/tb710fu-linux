#!/usr/bin/env python3
"""TB710FU: 在板级 DTS 里保留开机动画 framebuffer 与黑匣子两个槽位。

问题（已实测定位）
------------------
0xD5100000 起 25MiB 是 bootloader 的开机动画 framebuffer。内核里有一套自绘的
启动调试设施，用固定物理地址 __va(0xd5100000) 往这块画东西：
  - 引导梯子的彩色色块（tb_mark）
  - 面板控制台（tbfb，8x16 字形放大 4 倍）
  - 每 10 秒一次的心跳仪（tb_gauge_draw，绿方块 + 红标记）
  - initcall 进度条（tb_initcall_bar / tb_mem_bar）
  - 黑匣子底部状态带
同一块内存里的 0xB0000000 / 0xD6A00000 各 1MiB 是黑匣子的日志环（tb_bb_pa[]）。

这些节点本来是 U-Boot 加的（common/board_r.c），但那段代码有两个 bug：

    u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };
    fdt_setprop(fdt, fn, "reg", reg, sizeof(reg));   /* ① */
    fdt_setprop_empty(fdt, fn, "no-map");            /* ② */

 ① fdt_setprop() 把小端主机内存里的 u32 数组原样拷进大端的 DTB，于是每个 cell
    字节反序：0xd5100000 -> 0x000010d5，0x01900000 -> 0x00009001。内核忠实照做，
    去保留 0x10d5 处 36865 字节（不是 RAM），真正那 25MiB 一个字节都没保留。
    内核日志里的荒唐地址 "framebuffer at 0x1045, 0x9001 bytes" 就是它。
 ② no-map 会把该区从线性映射里剔除，一旦 ① 修好，__va(0xd5100000) 立刻翻译失败。

后果：这 25MiB 被页分配器当普通 System RAM 发放（/proc/iomem 里就是
"d5100000-d7bfffff : System RAM"），分配到这儿的页缓存/匿名页随后被上面那套绘制
代码反复改写 —— 在大文件（>2GiB，此时分配器才会回落到低地址段）上表现为静默
数据损坏：读页缓存拿到的 md5 与磁盘不一致，而磁盘内容是对的。实测 2GiB 通过、
4GiB 失败，随占用概率时有时无。

修法
----
在本 DTS 里自己声明这些节点：U-Boot 只在节点"不存在"时才添加
（fdt_add_subnode 返回负值就什么都不做），所以这里声明了它就动不了我们。
必须不带 no-map —— 保留给驱动用，但仍留在内核线性映射里给 __va() 用。

用法: python3 patch-dts-fb-reserve.py [dts 路径]
"""
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else \
    'arch/arm64/boot/dts/qcom/sm8650-lenovo-tb710fu.dts'

NODES = """\
		/* TB710FU: bootloader splash framebuffer.  The kernel's boot
		 * console, liveness gauge and initcall bar draw into it at a fixed
		 * physical address (0xd5100000); see tb_mark()/tbfb in
		 * init/main.c.  U-Boot adds this node itself, but writes its reg
		 * byte-swapped (it lands as base 0x10d5 size 0x9001, reserving
		 * nothing) and marks it no-map.  Declaring it here wins, because
		 * U-Boot only fills in a node that is missing.
		 *
		 * Reserved, and deliberately NOT no-map: the drawing code reaches
		 * it through __va(), which needs the region in the linear map.
		 *
		 * Without the reservation the page allocator hands these pages out
		 * as page cache and the drawing code then overwrites whatever was
		 * allocated there -- silent corruption of large files.
		 */
		framebuffer_mem: framebuffer@d5100000 {
			reg = <0x00 0xd5100000 0x00 0x1900000>;
		};

		/* TB710FU: the two rings the boot log black box appends to
		 * (tb_bb_pa[] in init/main.c).  Same rule: reserved, not no-map.
		 */
		blackbox_a_mem: tb-blackbox-a@b0000000 {
			reg = <0x00 0xb0000000 0x00 0x100000>;
		};

		blackbox_b_mem: tb-blackbox-b@d6a00000 {
			reg = <0x00 0xd6a00000 0x00 0x100000>;
		};

"""

s = open(PATH, encoding='utf-8', errors='surrogateescape').read()

if 'tb-blackbox-a@b0000000' in s:
    print('%s: already patched' % PATH)
    sys.exit(0)

key = 'reserved-memory {'
i = s.index(key)
j = s.index('{', i)
depth = 0
k = j
while k < len(s):
    if s[k] == '{':
        depth += 1
    elif s[k] == '}':
        depth -= 1
        if depth == 0:
            break
    k += 1
assert depth == 0, 'unbalanced braces'

s = s[:k] + NODES + s[k:]
open(PATH, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('%s: reserved-memory nodes added before offset %d' % (PATH, k))
