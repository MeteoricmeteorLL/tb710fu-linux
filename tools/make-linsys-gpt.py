#!/usr/bin/env python3
# linsys 重划 GPT 生成（sda = 4096 字节逻辑扇区 UFS LUN）
#   抹 sda14(userdata) + sda15(linroot) -> linboot 1GiB + linsys 128GiB + userdata(余量 85.71GiB)
# 输入: tmp/gpt-live-head.bin (LBA0..5) + tmp/gpt-live-tail.bin（2026-10-05 活体抓取）
# 输出: lab-state/gpt-linsys-head.bin (24KB -> dd 4K扇区 seek=0)
#       lab-state/gpt-linsys-tail.bin (20KB -> dd 4K扇区 seek=61390843)
import struct, uuid, zlib

SEC = 4096
DISK_LBAS = 491126784 // 8          # 61390848
crc32 = lambda b: zlib.crc32(b) & 0xFFFFFFFF

LINUX_FS = uuid.UUID("0fc63daf-8483-4772-8e79-3d69d8477de4")

d = open(r"D:\zcodeproject\tb710fu\tmp\gpt-live-head.bin", "rb").read()
tail = open(r"D:\zcodeproject\tb710fu\tmp\gpt-live-tail.bin", "rb").read()
assert d[510:512] == b"\x55\xaa", "MBR 签名缺失"
hdr = d[SEC:2*SEC]
assert hdr[:8] == b"EFI PART", f"4K LBA1 非 GPT 头: {hdr[:8]}"
my_lba, alt_lba, first_u, last_u = struct.unpack("<QQQQ", hdr[24:56])
disk_guid = uuid.UUID(bytes_le=hdr[56:72])
ent_lba = struct.unpack("<Q", hdr[72:80])[0]
ne, es = struct.unpack("<II", hdr[80:88])
assert (my_lba, alt_lba) == (1, DISK_LBAS - 1), (my_lba, alt_lba)
assert (first_u, last_u) == (6, 61390842), (first_u, last_u)
assert (ent_lba, ne, es) == (2, 32, 128), (ent_lba, ne, es)   # 原厂表就是 32 条目×128B = 1 扇区
print(f"disk={DISK_LBAS}x4KB usable=[{first_u},{last_u}] guid={disk_guid}")

entries = bytearray(d[2*SEC : 2*SEC + ne*es])
def parse(e):
    t = uuid.UUID(bytes_le=e[0:16]); g = uuid.UUID(bytes_le=e[16:32])
    f, l = struct.unpack("<QQ", e[32:48])
    attr = struct.unpack("<Q", e[48:56])[0]
    return t, g, f, l, attr, e[56:128].decode("utf-16-le").rstrip("\x00")
for i in range(16):
    t, g, f, l, a, n = parse(bytes(entries[i*es:(i+1)*es]))
    if t.int == 0 and not n: continue
    print(f"  [{i+1:2d}] {n:<14} [{f}, {l}] attr=0x{a:016x} type={t}")

# --- 校验旧 14/15 正是预期布局，然后把 14/15/16 全部重写 ---
old14 = parse(bytes(entries[13*es:14*es])); old15 = parse(bytes(entries[14*es:15*es]))
assert old14[5] == "userdata" and old14[2] == 5105064 and old14[3] == 44613631, old14
assert old15[5] == "linroot" and old15[2] == 44613632 and old15[3] == 61390842, old15
UD_TYPE = old14[0]                    # 安卓 userdata 原类型 GUID 原样沿用

NEW = [  # (编号, 名称, first, last, type)
    (14, "linboot", 5105064,   5367207,  LINUX_FS),
    (15, "linsys",  5367208,  38921639,  LINUX_FS),
    (16, "userdata", 38921640, 61390842, UD_TYPE),
]
for idx, name, f, l, t in NEW:
    e = bytearray(es)
    e[0:16] = t.bytes_le
    e[16:32] = uuid.uuid4().bytes_le
    struct.pack_into("<QQ", e, 32, f, l)
    e[56:56+len(name)*2] = name.encode("utf-16-le")
    entries[(idx-1)*es : idx*es] = e
for i in range(16, ne):              # 17..128 清零
    entries[i*es:(i+1)*es] = bytes(es)

arr_crc = crc32(bytes(entries))
def mk_header(my, alt, el):
    h = bytearray(hdr)
    h[24:40] = struct.pack("<QQ", my, alt)
    h[72:80] = struct.pack("<Q", el)
    struct.pack_into("<I", h, 88, arr_crc)
    h[92:512] = bytes(512 - 92)
    h[16:20] = b"\0\0\0\0"
    struct.pack_into("<I", h, 16, crc32(bytes(h[:92])))
    return h

n_ent_sectors = (ne*es + SEC - 1) // SEC      # 1（32×128B 恰好一扇区）
head_bin = d[:SEC] + bytes(mk_header(1, DISK_LBAS-1, ent_lba)) + bytes(entries[:n_ent_sectors*SEC])
bak_lba0 = DISK_LBAS - 1 - n_ent_sectors      # 61390846
tail_bin = bytes(entries) + bytes(mk_header(DISK_LBAS-1, 1, bak_lba0))
assert len(tail_bin) == n_ent_sectors*SEC + SEC

open(r"D:\zcodeproject\tb710fu\lab-state\gpt-linsys-head.bin", "wb").write(head_bin)
open(r"D:\zcodeproject\tb710fu\lab-state\gpt-linsys-tail.bin", "wb").write(tail_bin)
print(f"\nhead {len(head_bin)}B -> dd bs=4096 seek=0")
print(f"tail {len(tail_bin)}B -> dd bs=4096 seek={bak_lba0}")

# --- 自校验: 重新解析产物 ---
for tag, blob, hdr_off in (("head", head_bin, SEC), ("tail", tail_bin, n_ent_sectors*SEC)):
    h = blob[hdr_off : hdr_off+SEC]
    c = struct.unpack("<I", h[16:20])[0]
    h2 = bytearray(h); h2[16:20] = b"\0\0\0\0"
    assert crc32(bytes(h2[:92])) == c, f"{tag} header CRC mismatch"
    el = struct.unpack("<Q", h[72:80])[0]
    arr = blob[el*SEC - (0 if tag=="head" else 0):][:ne*es] if tag=="head" else blob[:ne*es]
    ac = struct.unpack("<I", h[88:92])[0]
    assert crc32(bytes(arr)) == ac, f"{tag} entries CRC mismatch"
print("self-check: primary+backup header/entries CRC 全部通过")
for idx, name, f, l, t in NEW:
    print(f"  [{idx:2d}] {name:<14} [{f}, {l}] {(l-f+1)*SEC/2**30:.2f}GiB")
