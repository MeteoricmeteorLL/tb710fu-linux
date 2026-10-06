#!/usr/bin/env python3
# TB710FU: ABL cannot decompress a huge (>~80MB) blob, so the appended
# kernel is stored COMPRESSED and U-Boot gunzips it to 0xA8000000 itself.
#   gz kernel @0xA4000000, initramfs @0xA4E4C000, our DTB @0xA4F4C000
#   decompressed kernel target: 0xA8000000
f = '/home/meteor/u-boot-13r/common/board_f.c'
s = open(f).read()

start = s.index('\t\t(void)k;\n')
end_marker = '\t\tfor (;;)\n\t\t\t;\n'
end = s.index(end_marker, start) + len(end_marker)

new = '''\t\t(void)k;
\t\t/* ABL chokes on the >80MB fully-expanded blob, so the kernel is
\t\t * appended COMPRESSED; decompress it here and verify it landed. */
\t\t{
\t\t\tunsigned long gzlen = 14988551UL;
\t\t\tunsigned *kp = (unsigned *)0xA8000000UL;
\t\t\tunsigned *dp = (unsigned *)0xA4F4C000UL;
\t\t\tunsigned *fb = (unsigned *)0xD5100000UL;
\t\t\tint rc, r, c;
\t\t\tunsigned ok;

\t\t\trc = gunzip((void *)0xA8000000UL, 0x4000000,
\t\t\t\t    (unsigned char *)0xA4000000UL, &gzlen);
\t\t\tok = (rc == 0) && (kp[0x38 / 4] == 0x644d5241) &&
\t\t\t     (dp[0] == 0xedfe0dd0);

\t\t\t/* check block: GREEN = kernel+DTB good, RED = bad */
\t\t\tfor (r = 0; r < 200; r++) {
\t\t\t\tunsigned *line = fb +
\t\t\t\t\t(ulong)(100 + r) * 3200 + 2200;

\t\t\t\tfor (c = 0; c < 400; c++)
\t\t\t\t\tline[c] = ok ? 0xFF00FF00u : 0xFFFF0000u;
\t\t\t}
\t\t\tif (!ok) {
\t\t\t\tfor (;;)
\t\t\t\t\t;
\t\t\t}
\t\t}
\t\t/* Same sequence U-Boot's own booti uses: cleanup (flush caches,
\t\t * MMU off) then the assembly kernel-entry primitive. */
\t\tcleanup_before_linux();
\t\tarmv8_switch_to_el2(0xA4F4C000UL, 0, 0, 0, 0xA8000000UL,
\t\t\t\t    ES_TO_AARCH64);
\t\tfor (;;)
\t\t\t;
'''
s = s[:start] + new + s[end:]
if '#include <gzip.h>' not in s:
    s = s.replace('#include <common.h>', '#include <common.h>\n#include <gzip.h>', 1)
open(f, 'w').write(s)
print('gunzip-based kernel load installed')