# From a stock tablet / 从原厂机器开始

For a **stock TB710FU** — Android still installed, nothing partitioned, no
recovery flashed.  It ends where `docs/INSTALL.md` begins, so read the two
together: this document gets you a shell and a backup, that one installs Linux.

面向**原厂状态的 TB710FU** —— 安卓还在、分区没动过、也没刷 recovery。本文结束的地方
正是 `docs/INSTALL.md` 的起点：本文负责把你带到"有 shell、有备份"的状态，那边负责
装系统。

**Prerequisite: the bootloader must already be unlocked.**  That is a one-way change
(it trips the hardware fuse) and it wipes the device; how to do it is specific to
the model, and it is outside this repository.

**前提：引导程序必须已经解锁。** 解锁是单向的（会烧断硬件保险丝）且会清空设备；怎么
解锁与机型相关，不在本仓库范围内。

## 0. What is different here / 与 INSTALL.md 的差别

Nothing about the install changes; two things come first, because a stock device is
the only state in which they are possible:

安装流程本身一样，只是有两件事必须先做 —— 只有在原厂状态下才有机会做：

1. **Get a shell with `dd`** (§1) — preferably without flashing a recovery.
2. **Back up the stock partitions** (§2) — the only chance you get.

Then install from **`docs/INSTALL.md`** §1–3.

In this project those two steps had already been done before we started (a
community TWRP on `recovery_a`, the stock images pulled), so §1 is written as the
general route for this SoC family rather than a procedure we ran ourselves.

本项目开始前这两步已经做完了（社区 TWRP 刷在 `recovery_a`、原厂镜像已导出），所以
§1 写的是这类高通机型的通用做法，而不是我们亲手跑过的流程。

## 1. A shell with `dd` / 一个带 `dd` 的 shell

Everything from `docs/INSTALL.md` §1 on runs from such a shell.  Two ways, in
order of preference:

后面（`docs/INSTALL.md` 第 1 步起）所有命令都在这样的 shell 里跑。按推荐顺序两种：

**(a) Boot a recovery image without flashing it / 临时启动一个 recovery 镜像**

```sh
fastboot boot twrp.img      # runs from RAM; nothing is written to flash
```

If that works you get adb and a terminal and flash stays untouched —
`recovery_a` keeps whatever Lenovo put there.  If your bootloader refuses
`fastboot boot` (some do), fall back to (b).

如果可用，你会得到 adb 和终端，且**不写 flash** —— `recovery_a` 保持原样。若引导程序
不支持 `fastboot boot`（有些机型会拒绝），就用 (b)。

**(b) Flash a recovery / 刷入一个 recovery**

```sh
fastboot flash recovery_a twrp.img     # or recovery, depending on the image
```

This **overwrites `recovery_a`** — which is exactly what happened on our device,
and why this port keeps the DTB inside `linboot` rather than in a recovery
partition.  Keep a copy of what you overwrote if you can.

这会**覆盖 `recovery_a`** —— 我们的设备就是这样，也正因如此本移植把 DTB 放在
`linboot` 而不是 recovery 分区。能备份就先备份被覆盖的内容。

> **No recovery image is distributed with this repository.**  TWRP builds for this
> device exist in the community; take one from whoever publishes it, under their
> terms.
> **本仓库不提供任何 recovery 镜像。** 社区有本机型的 TWRP 构建，请从发布者处按其
> 条款获取。

## 2. Back up the stock side / 先备份原厂侧

Do this before touching any partition.  From the recovery shell, dump the
partitions you might want back, and pull them off the device:

动任何分区之前先做这一步。在 recovery shell 里把可能想恢复的分区导出并拉出设备：

```sh
mkdir -p /sdcard/stock
for p in boot_a vendor_boot_a dtbo_a vbmeta_a vbmeta_system_a persist modem \
         fsg fsc abl xbl_a xbl_config_a; do
    [ -b /dev/block/by-name/$p ] && dd if=/dev/block/by-name/$p of=/sdcard/stock/$p.img
done
sgdisk --backup=/sdcard/stock/gpt-stock.bin /dev/sda
sync
# then, from the PC:
adb pull /sdcard/stock ./stock-backup
```

* `persist` and the `modem`/`fsg` set carry per-device calibration; they are the
  ones people regret losing.
* `sgdisk --backup` gives you a one-command way back to the stock partition table.
* The Linux side never touches `boot_a`, `vendor_boot_a`, `dtbo_a` or `vbmeta*`:
  this port only writes `boot_b`, `linboot`, `linsys` and the `misc` marker.  So a
  stock Android can be kept bootable next to Linux.
* Nothing needs computing by hand: `docs/INSTALL.md` §1 has ready-made rows for
  the 256 GB variant and a snippet that derives the same numbers for any capacity,
  reading the last usable sector from your own device.  Use it rather than
  guessing — the partition geometry is the one thing here you cannot undo.

* `persist` 与 `modem`/`fsg` 这组带的是单机校准数据，是最容易让人后悔没备份的。
* `sgdisk --backup` 让你可以用一条命令回到原厂分区表。
* Linux 侧**从不**碰 `boot_a`、`vendor_boot_a`、`dtbo_a`、`vbmeta*`，只写 `boot_b`、
  `linboot`、`linsys` 和 `misc` 标记 —— 所以原厂安卓可以继续与 Linux 并存启动。
* 不需要手算：`docs/INSTALL.md` 第 1 节给了 256GB 版本的现成数值，也给了能按任意容量
  推导同样数字的脚本（最后一个可用扇区直接从你自己的设备读）。请用它，别猜 ——
  分区几何是这里唯一无法反悔的东西。

## 3. Now install / 开始安装

* partitions, boot chain, rootfs → **`docs/INSTALL.md`** §1–3
* first boot and what to expect → **`docs/INSTALL.md`** §3 (path A)
* going back to Android → **`docs/INSTALL.md`** §4
* if it does not boot → **`docs/INSTALL.md`** §5

## 4. Two honest notes / 两句实话

* **A locked bootloader cannot be restored.**  On this platform unlocking is
  irreversible; "put it back to stock" means "flash stock images onto an unlocked
  device", which is fine, but the unlock marker stays.
  **无法把引导程序重新锁回去** —— 这类平台上解锁不可逆；"恢复原厂"只能理解为
  "在已解锁设备上刷回原厂镜像"，解锁标记会一直保留。
* **Read `docs/KNOWN-ISSUES.md` before you commit your only tablet to this.**  The
  port works, but the speaker sound is distorted, WiFi is slow (and can take the
  machine down), and suspend has never been tried.  `docs/STATUS.md` has the
  per-subsystem picture.
  **如果这是你唯一的平板，动手前先读 `docs/KNOWN-ISSUES.md`。** 移植可用，但扬声器
  声音很炸、WiFi 慢（且可能把机器搞死）、suspend 从未试过。各部位情况见
  `docs/STATUS.md`。
