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
getting a recovery shell and backing up the stock partitions — which this document
assumes you already have.  (Either way the bootloader has to be unlocked.)

**如果机器还是原厂状态**，请先走 `docs/INSTALL-FROM-ZERO.md`：那里讲怎么拿到带 `dd`
的 shell、以及**先备份原厂分区**；这些本文默认你已经具备。（两种情况都要求引导程序
已解锁。）

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

### The layout / 布局

Three partitions matter, and only one of them has a size you have to think about.
Every number below is in **4096-byte logical sectors**, because that is what this
UFS reports — check with `sgdisk --print /dev/sda` before you touch anything.

三个分区是关键，其中只有一个的大小需要你决定。下面所有数字都是 **4096 字节逻辑
扇区**（这台 UFS 报的就是这个），动手前先用 `sgdisk --print /dev/sda` 核对。

| # | name | what it is / 是什么 | size / 大小 |
|---|---|---|---|
| 14 | `linboot` | the raw boot slot U-Boot reads at fixed offsets: kernel@0 (16 MiB window), initramfs@16 MiB (8 MiB window), DTB@24 MiB (160 KiB window) / U-Boot 按固定偏移读取的裸引导槽 | **keep 1 GiB.** The three windows end at 24.2 MiB, so 64 MiB would do; 1 GiB is what we use and leaves room for a bigger DTB or a spare kernel / **保持 1GiB**（三个窗口到 24.2MiB 为止，64MiB 也够；我们用 1GiB，留余量） |
| 15 | `linsys` | the Linux root filesystem, ext4 / Linux 根文件系统 | **your call.** The shipped image extracts to 5.1 GiB, so 16 GiB is comfortable and 128 GiB is what we used / **由你决定**（镜像解包后 5.1GiB，16GiB 就够舒服，我们用 128GiB） |
| 16 | `userdata` | Android / 安卓 | **everything that is left** / **剩下的全部** |

The only boundary you are choosing is `linsys` ↔ `userdata`: more Linux means less
Android.  Decide once — moving that boundary later means deleting and recreating
both partitions, which loses both sides.

你要选的只有 `linsys` ↔ `userdata` 这一条界线：Linux 多一点、安卓就少一点。请一次
定好 —— 以后再挪这条界线，做法是删掉并重建这两个分区，两边数据都会没。

### Ready-made sizes for the 256 GB variant / 256GB 版本的几组现成数值

On this device `linboot` starts at sector 5 105 064 (right after the stock
partitions 1–13, which you keep) and is always 262 144 sectors (1 GiB).  Pick a
`linsys` size from the first column; the rest follows.

在本机上 `linboot` 从扇区 5 105 064 开始（紧接你要保留的原厂 1–13 号分区），固定
262 144 扇区（1GiB）。按第一列挑一个 `linsys` 大小，其余随之确定。

| `linsys` | first | last | `userdata` (Android) | first | last |
|---|---|---|---|---|---|
| 32 GiB | 5 367 208 | 13 725 815 | 181.8 GiB | 13 725 816 | 61 390 842 |
| 64 GiB | 5 367 208 | 22 144 423 | 149.7 GiB | 22 144 424 | 61 390 842 |
| **128 GiB** (what we use) | 5 367 208 | 38 921 639 | 85.7 GiB | 38 921 640 | 61 390 842 |
| 192 GiB | 5 367 208 | 55 698 855 | 21.7 GiB | 55 698 856 | 61 390 842 |

The table stops at sector 61 390 842, six sectors short of the end of the device
(61 390 848 sectors): the backup GPT lives in the last few, so leave them alone.
If the `UD_LAST` you read from your own device is a few sectors higher, using it
is fine — the difference is under 32 KiB.

表里停在扇区 61 390 842，比本机总扇区数 61 390 848 少 6 个：备份 GPT 占最后几个扇区，
别去动它。若你从自己设备读到的 `UD_LAST` 比这大几个扇区，直接用也没问题 —— 差值不到
32KiB。

### Compute your own / 自己算

```sh
# in the recovery shell -- only LINSYS_GIB is yours to pick
LINSYS_GIB=128
LB_FIRST=5105064                       # one sector after the last partition you keep
LB_SECT=262144                         # 1 GiB
LS_FIRST=$((LB_FIRST + LB_SECT))
LS_LAST=$((LS_FIRST + LINSYS_GIB * 262144 - 1))
UD_FIRST=$((LS_LAST + 1))
UD_LAST=$(sgdisk --print /dev/sda | sed -n 's/.*last usable sector is \([0-9]*\).*/\1/p')
printf 'linboot  %s..%s\nlinsys   %s..%s\nuserdata %s..%s\n' \
       "$LB_FIRST" "$((LS_FIRST - 1))" "$LS_FIRST" "$LS_LAST" "$UD_FIRST" "$UD_LAST"
```

* `UD_LAST` is read from the device, so this works on a different capacity too.
* If partitions 1–13 are laid out differently, take `LB_FIRST` from
  `sgdisk --print` as "one sector after the last partition you keep".
* The three numbers you computed are what go into the `--new=` arguments below.

* `UD_LAST` 是从设备读的，所以换容量也适用。
* 如果 1–13 号分区布局不同，`LB_FIRST` 就从 `sgdisk --print` 里取"你要保留的最后一个
  分区的下一个扇区"。
* 算出来的三组数字，就是下面 `--new=` 要填的东西。

### The commands / 命令

```sh
# in the recovery shell
sgdisk --print /dev/sda                       # note the current userdata TYPE GUID
sgdisk --backup=/tmp/gpt-before.bin /dev/sda  # keep this file

sgdisk --delete=14 --delete=15 /dev/sda       # <- this erases them
sgdisk --new=14:5105064:5367207   --change-name=14:linboot  --typecode=14:8300 /dev/sda
sgdisk --new=15:5367208:38921639  --change-name=15:linsys   --typecode=15:8300 /dev/sda
sgdisk --new=16:38921640:61390842 --change-name=16:userdata --typecode=16:1B81E7E6-F50D-419B-A739-2AEEF8DA3335 /dev/sda
sgdisk --verify /dev/sda

# the kernel's view of the table: per partition, never a blanket `partx -u`
partx -d --nr 14 /dev/sda; partx -a --nr 14 /dev/sda; partx -a --nr 16 /dev/sda
grep -E 'sda1[4-6]' /proc/partitions          # sizes must match your table above
```

The numbers shown are the 128 GiB row — substitute whatever you computed.

上面的数字是 128GiB 那一组 —— 换成你自己算出来的。

* This device's `sgdisk` accepts **long options only** (`--new=`, not `-n`).
* `userdata` must keep Android's own **type GUID**.  On this device it is
  `1B81E7E6-F50D-419B-A739-2AEEF8DA3335`; take yours from the `--print` above.
  Android refuses to format the partition with a different type.
* `linboot` and `linsys` are plain Linux filesystem (`8300`).
* If a number does not come out as planned, stop and roll back:
  `sgdisk --load-backup=/tmp/gpt-before.bin /dev/sda`.
* Details, warnings and the rollback path: `docs/DEPLOY.md` §2.

* 这台设备上的 `sgdisk` **只认长选项**（`--new=`，不是 `-n`）。
* `userdata` 必须沿用安卓自己的**类型 GUID**；本机是
  `1B81E7E6-F50D-419B-A739-2AEEF8DA3335`，你的从上面那条 `--print` 里取。
  类型不对安卓会拒绝格式化该分区。
* `linboot` 与 `linsys` 用普通 Linux 文件系统类型（`8300`）。
* 任何数值和计划不符 → 停手回滚：`sgdisk --load-backup=/tmp/gpt-before.bin /dev/sda`。
* 细节、告警与回滚路径见 `docs/DEPLOY.md` 第 2 节。

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
