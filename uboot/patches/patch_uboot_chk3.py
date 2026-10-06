#!/usr/bin/env python3
# TB710FU: granular checks + smaller offsets.
#   gz kernel @0xA0800000 (8MB), initramfs @0xA164C000, DTB @0xA174C000
#   decompressed kernel target 0xA8000000
# Three stacked check blocks (top-right):
#   A: gunzip() returned 0
#   B: decompressed kernel has ARM64 magic
#   C: our DTB is present at its address
f = '/home/meteor/u-boot-13r/common/board_f.c'
s = open(f).read()

start = s.index('\t\t(void)k;\n')
end_marker = '\t\tfor (;;)\n\t\t\t;\n'
end = s.index(end_marker, start) + len(end_marker)

new = '''\t\t(void)k;
\t\t/* Kernel is appended compressed; decompress + verify here.
\t\t * Three stacked indicators (top-right): gunzip rc, kernel magic,
\t\t * DTB present -- GREEN = ok, RED = bad. */
\t\t{
\t\t\tunsigned long gzlen = 14988551UL;
\t\t\tunsigned *kp = (unsigned *)0xA8000000UL;
\t\t\tunsigned *dp = (unsigned *)0xA174C000UL;
\t\t\tunsigned *fb = (unsigned *)0xD5100000UL;
\t\t\tint rc, r, c;
\t\t\tunsigned ok[3];

\t\t\trc = gunzip((void *)0xA8000000UL, 0x4000000,
\t\t\t\t    (unsigned char *)0xA0800000UL, &gzlen);
\t\t\tok[0] = (rc == 0);
\t\t\tok[1] = (kp[0x38 / 4] == 0x644d5241);
\t\t\tok[2] = (dp[0] == 0xedfe0dd0);

\t\t\tfor (r = 0; r < 3; r++) {
\t\t\t\tint rr, cc;

\t\t\t\tfor (rr = 0; rr < 120; rr++) {
\t\t\t\t\tunsigned *line = fb +
\t\t\t\t\t\t(ulong)(100 + r * 140 + rr) * 3200 + 2200;

\t\t\t\t\tfor (cc = 0; cc < 400; cc++)
\t\t\t\t\t\tline[cc] = ok[r] ? 0xFF00FF00u
\t\t\t\t\t\t\t\t : 0xFFFF0000u;
\t\t\t\t}
\t\t\t}
\t\t\tif (!ok[0] || !ok[1])
\t\t\t\tfor (;;)
\t\t\t\t\t;
\t\t}
\t\tcleanup_before_linux();
\t\tarmv8_switch_to_el2(0xA174C000UL, 0, 0, 0, 0xA8000000UL,
\t\t\t\t    ES_TO_AARCH64);
\t\tfor (;;)
\t\t\t;
'''
s = s[:start] + new + s[end:]
open(f, 'w').write(s)
print('granular checks + 8MB offsets installed')