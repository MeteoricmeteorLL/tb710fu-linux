# Building the kernel / 重建内核

The shipped kernel is `7.2.0-gcf72cbb39da8-dirty`, built from mainline commit
`cf72cbb39da84b6f02f90c07f33b102fc10b16f0` plus the patches in this repository.
Its `Image.gz` is byte-identical to `kernel/Image.gz`
(md5 `3c4fe5d0921d510dc2ccab2bd91201a1`).

随附内核是 `7.2.0-gcf72cbb39da8-dirty`，基于主线
`cf72cbb39da84b6f02f90c07f33b102fc10b16f0` 加本仓库的补丁构建。它的 `Image.gz` 与
`kernel/Image.gz` 逐字节相同（md5 `3c4fe5d0921d510dc2ccab2bd91201a1`）。

## 1. Host / 宿主机

A Linux host or WSL with: `aarch64-linux-gnu-gcc` (gcc 15.2.0 was used),
`bison flex bc python3 libssl-dev libelf-dev`, ~30 GB free, and `git`.
`dtc` is built by the kernel itself; the DTB tools in `tools/` use the host's
`dtc` (`apt install device-tree-compiler`).

Linux 或 WSL，需要 `aarch64-linux-gnu-gcc`（当时用 gcc 15.2.0）、
`bison flex bc python3 libssl-dev libelf-dev`、约 30GB 空间、`git`。`dtc` 由内核
自己构建；`tools/` 里的 DTB 工具用宿主机的 `dtc`（`apt install device-tree-compiler`）。

## 2. Get the tree and apply everything / 取源码并打全补丁

```sh
git clone --depth 1 https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git
cd linux
git fetch --depth 1 origin cf72cbb39da84b6f02f90c07f33b102fc10b16f0
git checkout cf72cbb39da84b6f02f90c07f33b102fc10b16f0

git apply /path/to/kernel/patches/TB710FU-full-tree.diff
cp -r /path/to/kernel/sources/* .          # files the diff cannot carry
cp /path/to/kernel/config .config
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
```

`kernel/sources/` is not optional: the board DTS, the two panel drivers, the
Novatek touch driver, the AW3750x regulator and the AW882xx codec are **new
files**, so they are not in the diff.  `/lib/modules` on the device expects the
touched files.

`kernel/sources/` 不是可选项：板级 DTS、两个面板驱动、Novatek 触摸驱动、AW3750x
稳压器和 AW882xx 功放都是**新增文件**，diff 里没有。

The diff is regenerated from the working tree, so it includes the GPU fix that
earlier revisions of it were missing: `a6xx_catalog.c` drops
`ADRENO_QUIRK_IFPC` and `a750_ifpc_reglist` for chip id `0x43051401`
("C520v2", Adreno 750 / gen70900), which is what stops the GMU fence timeouts
that froze the machine (`docs/KNOWN-ISSUES.md` §4.1).

这份 diff 是从工作树重新生成的，因此包含了早期版本漏掉的 GPU 修复：
`a6xx_catalog.c` 为芯片 id `0x43051401`（Adreno 750 / gen70900）去掉了
`ADRENO_QUIRK_IFPC` 与 `a750_ifpc_reglist`，这是让 GMU 栅栏超时不再把机器冻住的
关键（见 `docs/KNOWN-ISSUES.md` 第 4.1 节）。

Config values worth knowing / 值得注意的配置项:

| | why / 原因 |
|---|---|
| `CONFIG_DRM_MSM=y`, `CONFIG_DRM_PANEL_*` | the panel must come up before userspace / 面板要在用户态之前亮 |
| `CONFIG_EXTRA_FIRMWARE=…` | GPU firmware built in, so the first frames appear early / GPU 固件内建，早期就有画面 |
| `CONFIG_SQUASHFS_XZ/ZSTD/XATTR=y`, `CONFIG_LSM="…,apparmor,…"` | so `snap`'s squashfs and AppArmor are not the reason it fails / 免得 snap 的失败被误判成内核缺项 |
| `CONFIG_ARM64_4K_PAGES=y` | matches the vendor firmware / 与厂商固件一致 |

## 3. Build / 编译

```sh
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image.gz dtbs modules
```

Outputs / 产物:

* `arch/arm64/boot/Image.gz` → `kernel/Image.gz` (md5 above)
* `arch/arm64/boot/dts/qcom/sm8650-lenovo-tb710fu.dtb` → into the `linboot` slot
* modules under the build tree → into `/lib/modules/7.2.0-gcf72cbb39da8-dirty/`

The Novatek touch driver builds out of tree as well (it is a separate module in
the running system):

```sh
cd /path/to/sources/drivers/input/touchscreen/NT36XXX_SPI
make -C /path/to/linux M=$PWD ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules
```

## 4. Putting it on the device / 装到设备上

The `linboot` partition is a raw slot with fixed windows — U-Boot reads exactly
these, so an oversized file is silently truncated:

| offset | window | contents |
|---|---|---|
| 0 | 16 MiB | `Image.gz` |
| 16 MiB | 8 MiB | initramfs (leave the shipped one alone unless you rebuilt it) |
| 24 MiB | 160 KiB | DTB |

```sh
# kernel
dd if=Image.gz of=/dev/block/by-name/linboot bs=4096 seek=0 conv=fsync
# DTB - and make sure it carries the three reserved-memory nodes!
dd if=sm8650-lenovo-tb710fu.dtb of=/dev/block/by-name/linboot bs=4096 seek=6144 conv=fsync
sync
```

**Always check the DTB for the fix before installing it** — the corruption in
`KNOWN-ISSUES.md` §1 comes back with any DTB that lacks it:

```sh
dtc -I dtb -O dts sm8650-lenovo-tb710fu.dtb | grep -A2 'framebuffer@d5100000'
#   reg = <0x00 0xd5100000 0x00 0x1900000>;      <- no no-map
```

If the DTS you build from does not have them, apply
`tools/patch-dts-fb-reserve.py` to it (or run `tools/fix-dtb-fb-reserve.py` on a
DTB you already have).  Note that a DTB taken from the *running* system already
contains U-Boot's edits (bootargs, memory banks, uart status) — that is expected,
and `fix-dtb-fb-reserve.py` handles exactly that case.

If your DTS does not have them, note that **U-Boot patches its own node into the
DTB at boot** unless one is already there — see `docs/BUILD-UBOOT.md` and
`uboot/patches/patch-uboot-fbreg.py`.

## 5. Modules and the rest / 模块与其余部分

```sh
# on the device, after copying /lib/modules/<version>/ across
depmod -a $(uname -r)
```

For the firmware, the board configuration and the services the system needs, see
`docs/ROOTFS.md` §1 and `board/README-board-root.md`: the shipped rootfs already
has them, and `board/board-root.tgz` restores them onto a different one.
