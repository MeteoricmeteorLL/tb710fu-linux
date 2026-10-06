# Installation / 安装教程

Two paths, same device layout:

* **A — this repository's rootfs** (Ubuntu 26.04 + Plasma 6, ready to flash)
* **B — your own rootfs / another distribution**

Both share steps 1–3: prepare the partitions, put U-Boot in `boot_b`, put the
kernel + initramfs + DTB in the `linboot` slot.  After that they differ only in
what gets unpacked onto the `linsys` partition.

两条路径，同一套设备布局：**A = 本仓库的 rootfs**（现成的 Ubuntu 26.04 + Plasma 6）、
**B = 你自己的 rootfs / 其他发行版**。第 1–3 步完全共用（分区、把 U-Boot 放进
`boot_b`、把内核+initramfs+DTB 放进 `linboot`），之后只是往 `linsys` 里解包的东西不同。

> Deeper references / 更细的参考：`docs/DEPLOY.md`（分区数值、冷启动、故障排查表）·
> `docs/ROOTFS.md`（换发行版时系统必须提供什么）· `docs/KNOWN-ISSUES.md`（先读）·
> `docs/STATUS.md`（各部位可用性）

**Starting from a stock tablet?**  Do `docs/INSTALL-FROM-ZERO.md` first: it covers
unlocking the bootloader, getting a recovery shell, and backing up the stock
partitions — which this document assumes you already have.

**如果机器还是原厂状态**，请先走 `docs/INSTALL-FROM-ZERO.md`：那里讲解锁引导程序、
拿到带 `dd` 的 shell、以及**先备份原厂分区**；这些本文默认你已经具备。

Two different shells appear below, and they are not the same thing:

下面会出现两种 shell，别混淆：

| shell | what it is / 是什么 |
|---|---|
| **recovery shell** | a third-party recovery (TWRP or similar) you boot or flash yourself; it has `adb` and `dd`.  Not shipped here. / 你自行启动或刷入的第三方 recovery（TWRP 等），有 `adb` 和 `dd`；本仓库不提供 |
| **rescue console** | the shell in this port's **initramfs**, on USB NCM at `192.168.7.2` (`nc 4444` / `telnet 4445`); it works even when the rootfs is missing or broken, and `/boot` there is the `linboot` partition. / 本移植 **initramfs** 里的救援控制台，走 USB NCM（`192.168.7.2`），rootfs 坏了也能用，里面 `/boot` 就是 `linboot` 分区 |

---

## 0. What you need / 准备

| item | where / 位置 |
|---|---|
| `release/linboot-20261006.img` (32 MiB) | kernel + initramfs + DTB slot image |
| `uboot/boot_b-linboot-v3.img` (615 KB) | U-Boot for `boot_b` |
| `release/tb710fu-rootfs-20261006.tar.zst` (2.0 GB) | path A: the root filesystem (GitHub release asset) |
| `release/CHECKSUMS.txt`, the manifest | verify the download (§6) |
| `board/board-root.tgz` (42 MB) | path B: firmware + modules + board configs + services |
| `firmware/tb710fu-firmware-*.tar.gz` (37 MB) | path B: just the vendor blobs |
| a recovery giving you a shell with `dd` and `adb` | **not shipped here** — bring your own |

Bootloader must be unlocked, and this procedure **wipes two partitions** (§1).
Please read `docs/KNOWN-ISSUES.md` first: it tells you what does *not* work yet
(speakers, WiFi speed) and why the boot framebuffer reservation matters.

需要解锁的引导程序；本流程**会抹掉两个分区**（见第 1 步）。动手前请先读
`docs/KNOWN-ISSUES.md`：里面写了目前哪些东西还不能用（扬声器、WiFi 速率），以及那个
framebuffer 保留为什么重要。

## 1. Partitions / 分区

The layout this port expects (all numbers in **4096-byte logical sectors**, which
is what this UFS reports — check with `sgdisk --print /dev/sda` first):

| # | name | first | last | size | contents |
|---|---|---|---|---|---|
| 14 | `linboot` | 5 105 064 | 5 367 207 | 1 GiB | raw boot slot: kernel@0, initramfs@16 MiB, DTB@24 MiB |
| 15 | `linsys` | 5 367 208 | 38 921 639 | 128 GiB | the Linux root filesystem (ext4) |
| 16 | `userdata` | 38 921 640 | 61 390 842 | 85.7 GiB | Android (it reformats this itself) |

```sh
# in the recovery shell
sgdisk --print /dev/sda                      # note the current userdata TYPE GUID
sgdisk --backup=/tmp/gpt-before.bin /dev/sda # keep this file

sgdisk --delete=14 --delete=15 /dev/sda      # <- this erases them
sgdisk --new=14:5105064:5367207   --change-name=14:linboot  --typecode=14:8300 /dev/sda
sgdisk --new=15:5367208:38921639  --change-name=15:linsys   --typecode=15:8300 /dev/sda
sgdisk --new=16:38921640:61390842 --change-name=16:userdata --typecode=16:<original userdata GUID> /dev/sda
sgdisk --verify /dev/sda

# the kernel's view of the table: per partition, never a blanket `partx -u`
partx -d --nr 14 /dev/sda; partx -a --nr 14 /dev/sda; partx -a --nr 16 /dev/sda
```

* This device's `sgdisk` accepts **long options only**.
* Keep Android's original **type GUID** for `userdata` or Android will refuse to
  format it.
* Details, warnings and the rollback path: `docs/DEPLOY.md` §2.

## 2. Boot chain / 引导链

```sh
# U-Boot into boot_b (boot_a keeps stock Android - do not touch it)
dd if=/dev/block/by-name/boot_b of=/tmp/boot_b-backup.img        # back up first
dd if=boot_b-linboot-v3.img of=/dev/block/by-name/boot_b bs=4096 conv=fsync

# kernel + initramfs + DTB into linboot
dd if=linboot-20261006.img of=/dev/block/by-name/linboot bs=4096 conv=fsync
sync

# verify what landed (the linboot image is 32 MiB = 8192 blocks)
dd if=/dev/block/by-name/linboot bs=4096 count=8192 of=/tmp/lb.img
md5sum /tmp/lb.img linboot-20261006.img
```

`linboot` is read by U-Boot at three fixed windows (16 MiB kernel / 8 MiB
initramfs / 160 KiB DTB), so an oversized file is silently truncated.  If you
build your own kernel or DTB later, write only that window
(`dd ... bs=4096 seek=<blocks> conv=notrunc`; kernel `seek=0`, DTB `seek=6144`).
**Check any DTB for the three `reserved-memory` nodes before installing it** — see
`docs/BUILD-KERNEL.md` §4.

## 3. The root filesystem / 根文件系统（两条路径共用）

```sh
mkfs.ext4 -L linsys -m 1 /dev/block/by-name/linsys
mkdir -p /mnt/linsys && mount /dev/block/by-name/linsys /mnt/linsys
```

### 3A — install this repository's rootfs / 安装本仓库的 rootfs

```sh
cd /mnt/linsys
zstd -dc /path/to/tb710fu-rootfs-20261006.tar.zst | tar --xattrs --numeric-owner -xpf -
sync
# verify the extraction against the manifest that came with the release
md5sum -c --quiet /path/to/tb710fu-rootfs-20261006.manifest.md5    # 75 175 files
```

`--xattrs` matters: without it binaries that rely on file capabilities (`ping`,
`passwd`, ...) lose them.  Then finish:

```sh
umount /mnt/linsys
dd if=/dev/zero of=/dev/block/by-name/misc bs=4096 count=1     # boot slot B
sync
reboot        # from a cold start: hold power ~15 s, then power on
```

**First boot / 首次启动** (~40–60 s to the desktop):

1. U-Boot splash, then a dark panel while the kernel boots;
2. brief kernel messages drawn on the panel, then SDDM — **root is auto-logged in**;
3. `tb-firstboot.service` generates the machine-id, ssh host keys and hostname;
4. networking: the USB NCM link is up (`192.168.7.2`), so
   `ssh root@192.168.7.2` (password `tb710fu` — **change it: `passwd`**);
5. WiFi: write `/etc/tb-wifi-credentials.conf` (`SSID=` / `PSK=`, `chmod 600`) and
   `systemctl start tb-wifi.service`.  First association after a cold boot takes
   ~110 s because `phy0` only appears then; see `docs/STATUS.md` for how slow it is.

### 3B — another rootfs / another distribution

The initramfs does not care which distribution it finds.  It looks for the GPT
partition named `linsys`, mounts it read-write as **ext4**, and if
**`/etc/os-release`** is inside it uses it as the real root (`switch_root`) and
mounts `linboot` at `/boot`.  If that file is missing it falls back to the legacy
squashfs path, so a half-written rootfs fails safe instead of bricking.

initramfs 不关心是哪个发行版：它按 GPT 分区名 `linsys` 找分区、以 **ext4** 读写挂载，
只要里面有 **`/etc/os-release`** 就当真实根（`switch_root`），并把 `linboot` 挂到
`/boot`；没有那个文件就回落到旧路径，写坏了也不会变砖。

```sh
# 1. any rootfs with /etc/os-release: a distro tarball, debootstrap, a cloud image...
tar --xattrs --numeric-owner -xpf my-distro-rootfs.tar -C /mnt/linsys

# 2. the board bits from this repository (kernel modules, firmware, configs, services)
tar xzf board/board-root.tgz -C /mnt/linsys
tar xzf firmware/tb710fu-firmware-20261005.tar.gz -C /mnt/linsys
```

Then make sure the new system actually uses them:

| requirement | why / 原因 |
|---|---|
| `/lib/modules/7.2.0-gcf72cbb39da8-dirty/` matches the kernel in `linboot` | otherwise WiFi, touch and audio drivers never load. `board-root.tgz` supplies them for the shipped kernel; `depmod -a` after unpacking / 否则 WiFi/触摸/音频驱动都不加载 |
| `/lib/firmware/` has the 29 blobs | GPU firmware missing = **black panel**; touch firmware missing = dead digitizer / GPU 固件缺失会黑屏 |
| `/etc/modprobe.d/ath12k-override.conf` | **required** for WiFi (forces the BDF entry name) / WiFi 必需 |
| `/etc/modprobe.d/cfg80211-regdom.conf` | without it 5 GHz is passive-scan only / 否则 5GHz 只能被动扫描 |
| `/etc/NetworkManager/conf.d/99-tb-wifi-unmanaged.conf`, `99-nodns.conf` | hand `wlp1s0` to `tb-wifi.service`; stop NM emptying `resolv.conf` |
| `/etc/tmpfiles.d/tb-x11.conf` | recreates `/tmp/.X11-unix` so XWayland works / X11 程序必需 |
| `upower.service.d/override.conf` + the PipeWire user units | the session runs as **root** and both hard-code `ConditionUser=!root` / 会话是 root，需覆盖 |
| the `tb-*` services (`board-root.tgz/etc/systemd/system/`) | panel latch, touch rebind, console quiet, WiFi kick, time sync / 面板闩锁、触摸重绑、控制台静音、WiFi 保活、校时 |

```sh
# after unpacking, from a chroot or on first boot:
depmod -a 7.2.0-gcf72cbb39da8-dirty
systemctl daemon-reload
systemctl enable tb-panel-cycle tb-touch-rebind tb-console-quiet tb-wifi tb-timesync tb-firstboot
```

What a foreign rootfs must provide (userspace bits, package expectations, what is
impossible on this port): **`docs/ROOTFS.md`**.  If you also want to replace the
kernel, build it with **`docs/BUILD-KERNEL.md`** — and keep the DTB fix.

换发行版时系统需要提供什么、以及本移植上做不到的事（`snap`/`flatpak` 类）见
`docs/ROOTFS.md`；若要连内核一起换，按 `docs/BUILD-KERNEL.md` 重建，**并保留 DTB 修复**。

## 4. Back to Android / 回到安卓

```sh
fastboot set_active a
fastboot erase misc
fastboot reboot      # then power on cold
```

Android reformats `userdata` on its first boot.  The Linux side stays where it is:
`fastboot set_active b` + `erase misc` brings it back.

## 5. If it does not boot / 起不来

| symptom / 现象 | likely cause / 原因 | fix / 处理 |
|---|---|---|
| nothing, not even U-Boot | `boot_b` write failed | re-flash it (§2); compare md5 |
| U-Boot runs, kernel never starts | DTB malformed / wrong linboot window | restore a known-good DTB (`dd ... seek=6144`) |
| backlight on, no picture | panel latch race | `tb-panel-cycle` (from the rescue console or ssh); the shipped service does it every boot |
| kernel text, then black | console vs compositor | `systemctl stop tb-console-quiet.service` to get the log back on the panel |
| rescue console only | `linsys` not ext4 / no `/etc/os-release` | redo §3; that is the deliberate fallback |
| boots, then freezes | see `docs/KNOWN-ISSUES.md` §4 | check `/sys/fs/pstore` and the previous boot's lines on the panel |

The rescue console is the thing to rely on: it lives in the initramfs, on USB NCM,
independent of the rootfs — from there `/boot` is the `linboot` partition, so you
can replace the kernel or DTB without a PC-side flasher.

救援控制台 是兜底手段：在 initramfs 里、走 USB NCM、不依赖 rootfs；在它里面 `/boot`
就是 `linboot` 分区，可以不带电脑直接换内核或 DTB。

## 6. Verify your download / 校验下载

```sh
sha256sum tb710fu-rootfs-20261006.tar.zst   # must match release/CHECKSUMS.txt
zstd -t tb710fu-rootfs-20261006.tar.zst     # "ok"
sh scripts/verify-rootfs.sh tb710fu-rootfs-20261006.tar.zst
# after deploying:
sh scripts/verify-rootfs.sh --deployed /mnt/linsys tb710fu-rootfs-20261006.manifest.md5
```
