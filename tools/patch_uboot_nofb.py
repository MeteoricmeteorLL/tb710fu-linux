"""Stop adding the simple-framebuffer node: it is what kills the kernel at ~3 s.

The log stops exactly at
    simple-framebuffer 1045.framebuffer: framebuffer at 0x1045, 0x9001 bytes
with a nonsense address in the node (the same shape as the 3.019 s crash that
has been unresolved since 追加 28, whose fault address was __va() of a garbage
physical address).  The node is added here by this routine; our kernel's panel
console writes to 0xD5100000 directly and needs no DT node at all, so drop it.

The /reserved-memory entry that keeps the page allocator off that buffer is kept
-- that part is what makes the console safe to keep using.
"""

import sys

P = '/home/meteor/u-boot-13r/common/board_r.c'
s = open(P, encoding='utf-8', errors='surrogateescape').read()

OLD = """\t\t\toff = fdt_add_subnode(fdt, 0, "framebuffer@d5100000");
\t\t\tif (off >= 0) {
\t\t\t\tu32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };

\t\t\t\tfdt_setprop_string(fdt, off, "compatible",
\t\t\t\t\t\t   "simple-framebuffer");
\t\t\t\tfdt_setprop_u32(fdt, off, "width", 3200);
\t\t\t\tfdt_setprop_u32(fdt, off, "height", 2000);
\t\t\t\tfdt_setprop_u32(fdt, off, "stride", 12800);
\t\t\t\tfdt_setprop_string(fdt, off, "format",
\t\t\t\t\t\t   "a8r8g8b8");
\t\t\t\tfdt_setprop(fdt, off, "reg", reg, sizeof(reg));
\t\t\t}
\t\t\ttb_logv("FB NODE", (ulong)(unsigned int)off);
"""
NEW = """\t\t\t/* TB710FU: deliberately no simple-framebuffer node.  The
\t\t\t * kernel's panel console writes to 0xD5100000 itself and
\t\t\t * needs none, while this node killed the boot at ~3 s:
\t\t\t * the log stopped right after
\t\t\t *   simple-framebuffer 1045.framebuffer: framebuffer at
\t\t\t *   0x1045, 0x9001 bytes
\t\t\t * i.e. with a nonsense address -- the same signature as the
\t\t\t * 3.019 s crash that was open since 追加 28. */
\t\t\ttb_screen_log("NO FB NODE", 2);
"""
if s.count(OLD) != 1:
    sys.exit('framebuffer block not found (%d)' % s.count(OLD))
s = s.replace(OLD, NEW)
open(P, 'w', encoding='utf-8', errors='surrogateescape').write(s)
print('board_r.c: simple-framebuffer node patch removed (reserved-memory kept)')
