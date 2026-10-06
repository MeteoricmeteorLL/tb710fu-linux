#!/usr/bin/env python3
"""TB710FU: fix the device-tree framebuffer reservation U-Boot adds at boot.

What was wrong (the root cause of the silent memory corruption in
docs/KNOWN-ISSUES.md §1):

    u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };
    int fn = fdt_add_subnode(fdt, off, "framebuffer@d5100000");
    if (fn >= 0) {
        fdt_setprop(fdt, fn, "reg", reg, sizeof(reg));   /* (1) */
        fdt_setprop_empty(fdt, fn, "no-map");            /* (2) */
    }

(1) fdt_setprop() copies the bytes of that array into the tree verbatim, and the
    tree's cells are big-endian, so on a little-endian host every cell came out
    reversed: 0xd5100000 landed as 0x000010d5 and 0x01900000 as 0x00009001.  The
    kernel dutifully reserved 36865 bytes at 0x10d5 -- not RAM -- and none of the
    real 25 MiB.  That is the nonsense address in the kernel log:
        framebuffer 1045.framebuffer: framebuffer at 0x1045, 0x9001 bytes
(2) no-map would drop the region out of the kernel's linear map, which the
    kernel's own drawing code (tb_mark / tbfb / gauge, all via
    __va(0xd5100000)) needs -- so it must not be there.

Consequence: /proc/iomem reported "d5100000-d7bfffff : System RAM", the page
allocator handed those pages out as page cache, and the console scribbled over
whatever had been allocated there -- silently corrupting large files (the failure
was size-dependent because the allocator only reaches this low region under
pressure).

What this patch does:

    * swaps the values with cpu_to_fdt32() before fdt_setprop() copies them, so
      the cells come out right (this U-Boot's libfdt has no fdt_setprop_cells());
    * drops no-map (reserved, but still mapped);
    * adds the two 1 MiB black box rings (tb_bb_pa[] in the kernel's init/main.c)
      with the same rule, so even an image without the DTB-side fix is safe.

Declaring the nodes in the DTB is enough on its own -- U-Boot only fills in a
node that is missing, which is what the shipped DTB relies on.  This patch fixes
the cause instead of depending on that.

Usage: python3 patch-uboot-fbreg.py [path to common/board_r.c]
       (default /home/meteor/u-boot-13r/common/board_r.c)
"""
import io
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else '/home/meteor/u-boot-13r/common/board_r.c'

s = io.open(P, encoding='utf-8', errors='surrogateescape').read()

if 'cpu_to_fdt32(0xd5100000)' in s:
    print('already patched - nothing to do')
    raise SystemExit(0)

DECL_RE = re.compile(r'u32 reg\[4\] = \{ 0, 0xd5100000, 0, 0x1900000 \};')
NOMAP_RE = re.compile(
    r'\n[ \t]*fdt_setprop_empty\(fdt, fn, "no-map"\);\n([ \t]*)\}')

NEW_DECL = (
    '/* TB710FU: the cells go into the tree verbatim and are big-endian,\n'
    '\t\t\t\t * so they must be swapped here.  Without cpu_to_fdt32() they\n'
    '\t\t\t\t * read back as 0x10d5/0x9001: the kernel then reserved 36 KB\n'
    '\t\t\t\t * in the wrong place instead of this 25 MiB, the allocator\n'
    '\t\t\t\t * handed the pages out, and the kernel console overwrote\n'
    '\t\t\t\t * them (see docs/KNOWN-ISSUES.md §1). */\n'
    '\t\t\t\tu32 reg[4] = { 0, cpu_to_fdt32(0xd5100000),\n'
    '\t\t\t\t\t       0, cpu_to_fdt32(0x1900000) };')

BB = (
    '/* TB710FU: the black box log rings (tb_bb_pa[] in the kernel\'s\n'
    '\t\t\t\t * init/main.c) need the same rule: reserved, so the allocator\n'
    '\t\t\t\t * keeps off them, and still mapped, because the kernel writes\n'
    '\t\t\t\t * them through __va().  This sits outside the if above on\n'
    '\t\t\t\t * purpose: a DTB that already declares the framebuffer node\n'
    '\t\t\t\t * makes fdt_add_subnode fail, and the rings are still ours. */\n'
    '\t\t\t\t{\n'
    '\t\t\t\t\tu32 bba_reg[4] = { 0, cpu_to_fdt32(0xb0000000),\n'
    '\t\t\t\t\t\t\t   0, cpu_to_fdt32(0x100000) };\n'
    '\t\t\t\t\tu32 bbb_reg[4] = { 0, cpu_to_fdt32(0xd6a00000),\n'
    '\t\t\t\t\t\t\t   0, cpu_to_fdt32(0x100000) };\n'
    '\t\t\t\t\tint bba = fdt_add_subnode(fdt, off, "tb-blackbox-a@b0000000");\n'
    '\t\t\t\t\tint bbb = fdt_add_subnode(fdt, off, "tb-blackbox-b@d6a00000");\n\n'
    '\t\t\t\t\tif (bba >= 0)\n'
    '\t\t\t\t\t\tfdt_setprop(fdt, bba, "reg", bba_reg, sizeof(bba_reg));\n'
    '\t\t\t\t\tif (bbb >= 0)\n'
    '\t\t\t\t\t\tfdt_setprop(fdt, bbb, "reg", bbb_reg, sizeof(bbb_reg));\n'
    '\t\t\t\t}')

if not DECL_RE.search(s):
    raise SystemExit('could not find the reg[4] declaration - inspect the file')
if not NOMAP_RE.search(s):
    raise SystemExit('could not find the no-map statement - inspect the file')

s = DECL_RE.sub(NEW_DECL, s, count=1)
s = NOMAP_RE.sub(lambda m: '\n' + m.group(1) + '}\n\n' + m.group(1) + BB, s)

io.open(P, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('patched %s: cells byte-swapped, no-map dropped, black box rings added' % P)
