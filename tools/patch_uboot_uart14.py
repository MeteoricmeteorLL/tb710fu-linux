#!/usr/bin/env python3
"""TB710FU: exempt uart14 (the WCN7850 bluetooth uart) from the U-Boot
memboot's blanket 'disable every geni uart' fixup.  The geni serial driver
enables the uart's clocks at probe, so the BT stack needs the node enabled."""
import io

P = "/home/meteor/u-boot-13r/common/board_r.c"
T = "\t"
s = io.open(P, encoding="utf-8", errors="surrogateescape").read()

old = (T * 4 + "u = -1;\n"
       + T * 4 + "while ((u = fdt_node_offset_by_compatible(fdt, u,\n"
       + T * 6 + "\"qcom,geni-uart\")) >= 0)\n"
       + T * 5 + "fdt_setprop_string(fdt, u, \"status\",\n"
       + T * 7 + "   \"disabled\");")

new = (T * 4 + "u = -1;\n"
       + T * 4 + "while ((u = fdt_node_offset_by_compatible(fdt, u,\n"
       + T * 6 + "\"qcom,geni-uart\")) >= 0) {\n"
       + T * 5 + "/*\n"
       + T * 5 + " * TB710FU: uart14 carries the WCN7850 bluetooth node.\n"
       + T * 5 + " * The geni serial driver enables its clocks at probe,\n"
       + T * 5 + " * so leave the node enabled for the BT stack instead\n"
       + T * 5 + " * of blanket-disabling every geni uart.\n"
       + T * 5 + " */\n"
       + T * 5 + "if (fdt_subnode_offset(fdt, u, \"bluetooth\") >= 0)\n"
       + T * 6 + "continue;\n"
       + T * 5 + "fdt_setprop_string(fdt, u, \"status\",\n"
       + T * 7 + "   \"disabled\");\n"
       + T * 4 + "}")

n = s.count(old)
assert n == 1, "anchor count %d" % n
s = s.replace(old, new)
io.open(P, "w", encoding="utf-8", errors="surrogateescape").write(s)
print("board_r.c patched: uart14 exempted from the geni-uart disable")
