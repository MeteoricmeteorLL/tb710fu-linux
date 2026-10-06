#!/usr/bin/env python3
"""从 U-Boot 树里剥掉 fastgunzip（缓存窗口 v2，未验证可用），回到板上在用的
uart14fix 状态基线。2026-10-05 重建 linboot 引导时用：用户确认 uart14fix 才是
正常可用版本，fastgunzip 只在树里、从未上板验证（PROJECT_STATE 风险预案以
uart14fix 为回滚目标）。

反向编辑的 old/new 字符串用 ast 直接从两个补丁脚本里提取（main 2 处 +
_fix_fastgunzip_anchors 3 处），逐条断言恰好出现一次。幂等。
"""
import ast
import re
import io
import sys

TREE = "/home/meteor/u-boot-13r"
BR = TREE + "/common/board_r.c"
SCRIPTS = [
    "/mnt/d/zcodeproject/tb710fu/tools/patch_uboot_fastgunzip.py",
    "/mnt/d/zcodeproject/tb710fu/tools/_fix_fastgunzip_anchors.py",
]

s = io.open(BR, encoding="utf-8", errors="surrogateescape").read()
if "tb_cache_window" not in s and "asm/armv8/mmu.h" not in s:
    print("already clean - no fastgunzip remnants")
    sys.exit(0)


def tuples_from(path):
    """提取脚本里 (old, new, what) 三元组。"""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    out = []
    for node in ast.walk(tree):
        lists = []
        if (isinstance(node, ast.Call) and len(node.args) > 1
                and isinstance(node.args[1], ast.List)):
            lists.append(node.args[1])          # patch(BR, [ ... ])
        if isinstance(node, ast.Assign) and node.value and isinstance(node.value, ast.List):
            lists.append(node.value)            # edits = [ ... ]
        for lst in lists:
            for el in lst.elts:
                if (isinstance(el, ast.Tuple) and len(el.elts) == 3
                        and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in el.elts)):
                    out.append(tuple(e.value for e in el.elts))
    return out


edits = []
for p in SCRIPTS:
    got = tuples_from(p)
    print(f"{p.rsplit('/', 1)[-1]}: {len(got)} tuple(s)")
    edits += got

applied = skipped = 0
for old, new, what in edits:
    if new and new in s:
        n = s.count(new)
        assert n == 1, f"{what}: new-string count={n}"
        s = s.replace(new, old)
        applied += 1
        print(f"reverted: {what}")
    elif old and old in s:
        skipped += 1
        print(f"already-reverted: {what}")
    else:
        print(f"not present (skip): {what}")

# 函数块兜底：文件里的 v2 函数体可能与脚本 new 串有出入，按结构整段还原
# （int tb_quiet_ub = 1; 到下一个 void tb_logv 声明之间全部还原为紧邻两行）。
if "tb_cache_window" in s:
    pat = re.compile(
        r"int tb_quiet_ub = 1;\n.*?void tb_logv\(const char \*label, ulong v\);",
        re.DOTALL)
    m = pat.search(s)
    assert m, "tb_cache_window function block not found by structure either"
    s = s[:m.start()] + ("int tb_quiet_ub = 1;\n"
                         "void tb_logv(const char *label, ulong v);") + s[m.end():]
    applied += 1
    print("reverted: tb_cache_window function (structural fallback)")

io.open(BR, "w", encoding="utf-8", errors="surrogateescape").write(s)
print(f"board_r.c: 已写回（reverted={applied}, already={skipped}）")

rem = [i + 1 for i, line in enumerate(s.split("\n")) if "tb_cache_window" in line
       or "asm/armv8/mmu.h" in line]
if rem:
    print(f"REMAINING tb_cache_window/mmu.h lines: {rem}")
    sys.exit(1)
print("clean: 无 fastgunzip 残留")
