# Building U-Boot / 重建 U-Boot

The U-Boot in `boot_b` is the **uart14fix** variant of the DanDrewCJ /
`u-boot-13r` lineage (U-Boot **2025.04-rc5**), patched here to boot the raw
`linboot` slot.  `uart14fix` means the Bluetooth UART (`uart14`) is left enabled;
without it Bluetooth has no transport.

`boot_b` 里的 U-Boot 是 DanDrewCJ / `u-boot-13r` 谱系的 **uart14fix** 变体
（U-Boot **2025.04-rc5**），并在这里打了补丁改为从裸 `linboot` 槽引导。uart14fix
指的是保留蓝牙所用的 `uart14` 串口 —— 没有它蓝牙就没有传输层。

`uboot/boot_b-linboot-v3.img` is the image that is on the device.
`uboot/boot_b-linboot-v3-fbreg.img` is the same source **plus** the framebuffer
reservation fix (`docs/KNOWN-ISSUES.md` §1) — it compiles and packs cleanly, but
it has **not** been flashed here, because the shipped DTB already neutralises the
bug.  Both are Android boot images (`ANDROID!`, 4096-byte header, gzipped
`u-boot.bin` payload) suitable for `fastboot flash boot_b`.

`uboot/boot_b-linboot-v3.img` 是设备上在用的镜像。
`uboot/boot_b-linboot-v3-fbreg.img` 是同一份源码**加上** framebuffer 保留修复
（`docs/KNOWN-ISSUES.md` 第 1 节）—— 它编译与打包都通过，但**没有**在本机刷入，
因为随附的 DTB 已经让那个 bug 失效。两者都是 Android boot 镜像
（`ANDROID!`、4096 字节头、gzip 过的 `u-boot.bin`），可直接
`fastboot flash boot_b`。

## 1. Source / 源码

The working tree is **not a git repository**: every TB710FU change lives as a file
edit, and the patches are frozen as idempotent `patch_uboot_*.py` scripts in
`uboot/patches/`.  The complete, buildable tree is
`uboot/u-boot-13r-src-20261006-fbreg.tar.gz`.

那棵工作树**不是 git 仓库**：每处 TB710FU 改动都以文件修改形式存在，补丁固化成
`uboot/patches/` 里幂等的 `patch_uboot_*.py`。完整可编译的树在
`uboot/u-boot-13r-src-20261006-fbreg.tar.gz`。

```sh
tar xzf uboot/u-boot-13r-src-20261006-fbreg.tar.gz -C ~     # gives ~/u-boot-13r
cd ~/u-boot-13r
```

If you start from upstream U-Boot 2025.04-rc5 instead, apply the patch scripts in
`uboot/patches/` in filename order; each one is idempotent and says what it does.
The important ones:

若从上游 U-Boot 2025.04-rc5 开始，就按文件名顺序应用 `uboot/patches/` 里的脚本，
每个都是幂等的并自带说明。关键几个：

| script | effect / 作用 |
|---|---|
| `patch_uboot_uart14.py` | keep `uart14` (Bluetooth) enabled while disabling the other GENI UARTs / 保留蓝牙串口 |
| `patch-uboot-linboot.py` | `memboot` reads the kernel/initramfs/DTB from `linboot` (sda14) instead of `recovery_b`/`recovery_a`: DTB at `+0x1800` blocks, window `0x28` blocks (160 KiB) / 改为从 linboot 读 |
| `patch_uboot_quiet_boot.py`, `patch_uboot_fastgunzip.py` | **must not be re-applied** — both were reverted here; the quiet build hid the boot ladder and the fast-gunzip build was not the working lineage / **不要再打**：两者都已回退 |
| `patch_uboot_fbreg.py` (this repo, `tools/`) | the byte-swap fix for the `framebuffer@d5100000` reservation + the two black-box rings / framebuffer 保留节点的字节序修复 |

## 2. Configure and build / 配置与编译

```sh
cp /path/to/uboot/config .config         # the exact .config of the working build
make ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)
```

* **`ARCH=arm`, not `arm64`.**  U-Boot has no `arch/arm64` directory: 64-bit
  builds use `arch/arm` with `CONFIG_ARM64=y` (the defconfig sets `CONFIG_ARM=y`
  and `CONFIG_ARM64=y`), and the result is an AArch64 ELF.  `ARCH=arm64` fails
  with `arch/arm64/Makefile: No such file or directory`.
  **是 `ARCH=arm`**：U-Boot 没有 `arch/arm64` 目录，64 位构建用 `arch/arm` 加
  `CONFIG_ARM64=y`，产物是 AArch64 ELF。
* Config: `configs/sm8650-lenovo-tb710fu{,-minimal,-mtp}_defconfig` also exist;
  the shipped `uboot/config` is authoritative.
* Output: `u-boot.bin` (the working build is 1 451 336 bytes; the fbreg one
  1 451 384).

## 3. Pack into a `boot_b` image / 打包成 boot_b 镜像

```sh
python3 uboot/patches/pack_uboot_image.py \
        uboot/boot_b-linboot-v3.img u-boot.bin boot_b-new.img
```

The image is a 4096-byte Android boot header whose `kernel_size` field (offset 8)
is the length of the gzipped payload — that is what ABL reads.  Verify:

```sh
python3 - <<'EOF'
import struct, gzip
d = open('boot_b-new.img','rb').read()
ks = struct.unpack('<I', d[8:12])[0]
print(d[:8], 'kernel_size', ks, 'gzip payload', len(d[4096:4096+ks]),
      'gunzips to', len(gzip.decompress(d[4096:4096+ks])))
EOF
```

## 4. Flash / 刷入

```sh
# fastboot
fastboot flash boot_b boot_b-new.img
# or from a recovery / root shell
dd if=boot_b-new.img of=/dev/block/by-name/boot_b bs=4096 conv=fsync
sync
```

**Then power-cycle cold** (hold power ~15 s, then power on).  A warm
`fastboot reboot` after touching `boot_b` fails on this board.  Never write this
to `boot_a` — that slot keeps Android.

## 5. Traps, each of them paid for once / 坑（每条都踩过）

1. **U-Boot runs at EL1**, so `armv8_switch_to_el2()` returns instead of
   switching and the kernel never starts (the screen stops at
   `JUMP → BOOT ABORTED`).  The working tree calls `kentry(dtb, NULL, NULL, NULL)`
   directly, per the arm64 boot protocol (`x0` = DTB, `x1…x3` = 0).
2. **`.bss` must be zero** when the kernel starts: the kernel only clears it in
   `early_map_kernel()`, after `primary_entry` has already read a `.data`
   variable from the early idmap code.  `board_r.c` zeroes the image tail itself.
3. **Only `init_sequence_r[0..14]` runs** — full `dm_autoprobe` hangs this board;
   everything after that is brought up by hand, with progress drawn on the panel.
4. **There is no serial console**: output is the panel (`0xD5100000`, 3200×2000,
   stride 3200, 32 bpp — the DTS `width` must match or every row skews), and the
   kernel's own console takes the framebuffer over later.
5. **diag builds do not boot.**  `uboot-diag*.bin` exists to be *photographed*:
   it prints the previous crash's PC/FAR/ESR from IMEM and then feeds the
   watchdog forever.  Flashing one looks exactly like a dead board.
6. **Memboot windows are fixed** (see the table in `docs/BUILD-KERNEL.md` §4):
   kernel 16 MiB at 0, initramfs 8 MiB at 16 MiB, DTB 160 KiB at 24 MiB.
7. **Keep the framebuffer reservation.**  Without it (no DTB node and no fbreg
   patch) large file writes on the running system are silently corrupted — that
   is `docs/KNOWN-ISSUES.md` §1, and it is not a userspace problem.
