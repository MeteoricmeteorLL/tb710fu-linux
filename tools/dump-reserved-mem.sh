#!/bin/sh
# 列出 /proc/device-tree/reserved-memory 每个节点的 base/size/no-map
cd /proc/device-tree/reserved-memory || exit 1
for d in */; do
  n=${d%/}
  [ -f "$n/reg" ] || continue
  r=$(od -An -tx1 -v "$n/reg" | tr -d ' \n')
  # reg 是 4 个 32bit 单元: <hi lo shi slo> (address-cells=2, size-cells=2)
  hi=$(printf '%d' 0x$(echo "$r" | cut -c1-8))
  lo=$(printf '%d' 0x$(echo "$r" | cut -c9-16))
  shi=$(printf '%d' 0x$(echo "$r" | cut -c17-24))
  slo=$(printf '%d' 0x$(echo "$r" | cut -c25-32))
  base=$((hi * 4294967296 + lo))
  size=$((shi * 4294967296 + slo))
  nm=""
  [ -e "$n/no-map" ] && nm=" [no-map]"
  printf '%-26s base=0x%x size=0x%x end=0x%x%s\n' "$n" "$base" "$size" "$((base + size - 1))" "$nm"
done
echo "=== linux,cma ==="
od -An -tx1 -v linux,cma/reg 2>/dev/null
[ -e linux,cma/no-map ] && echo "cma has no-map" || echo "cma: no no-map"
echo "=== framebuffer props ==="
ls -l framebuffer@d5100000/ 2>/dev/null
echo "=== chosen/bootargs ==="
tr -d '\0' < /chosen/bootargs 2>/dev/null
