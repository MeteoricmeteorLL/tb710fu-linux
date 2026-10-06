# From zero / 从零开始

For a **stock TB710FU** — Android still installed, bootloader possibly still
locked, nothing partitioned.  It ends where `docs/INSTALL.md` begins, so read the
two together: this document gets you a shell and a backup, that one installs
Linux.

面向**原厂状态的 TB710FU** —— 安卓还在、引导程序可能还没解锁、分区也没动过。本文
结束的地方正是 `docs/INSTALL.md` 的起点：本文负责把你带到"有 shell、有备份"的状态，
那边负责装系统。

> ⚠️ **Unlocking is a one-way door** (it trips the hardware fuse) and it wipes the
> device.  After it, the platform is permanently marked as unlocked.
> **解锁是单向的**（会烧断硬件保险丝）并会清空设备；解锁后设备永久带"已解锁"标记。

## 0. The four things to do first / 先做这四件事

1. **Unlock the bootloader** (§1) — one-way, wipes the device.
2. **Get a shell with `dd`** (§2) — a booted recovery, ideally without flashing one.
3. **Back up the stock partitions** (§3) — the only chance to do it.
4. Then follow **`docs/INSTALL.md`** §1–3 — partitioning, boot chain, rootfs.

In this project steps 1–3 had already been done when we started: the device was
unlocked, a community TWRP was flashed to `recovery_a`, and the stock images had
been pulled.  What follows for §1 and §2 is therefore the **general path for this
SoC family, not a procedure we ran ourselves** — treat it as a starting point and
check it against your model's own documentation.

本项目开始时第 1–3 步已经做完了（设备已解锁、社区 TWRP 刷在 `recovery_a`、原厂镜像
也已导出）。所以下面第 1、2 步写的是**这类高通机型的通用路径，而不是我们亲手跑过的
流程** —— 请把它当起点，并与你这个型号自己的文档对照。

## 1. Unlock the bootloader / 解锁引导程序

On Android: Settings → About tablet → tap *Build number* seven times, then
Developer options → **OEM unlocking: on**.  Connect USB, then:

在安卓里：设置 → 关于平板 → 连点"版本号"七次，然后开发者选项 → 打开 **OEM unlocking**。
连好 USB，然后：

```sh
adb devices                 # accept the RSA prompt on the device
adb reboot bootloader       # into fastboot
fastboot devices            # serial should appear
fastboot flashing unlock    # or: fastboot oem unlock
# confirm on the device screen - this erases userdata
fastboot reboot
```

* If `flashing unlock` is refused, the model needs Lenovo's own unlock route
  (a vendor tool/app, sometimes tied to a Lenovo account).  That is outside this
  repository; look it up for TB710FU.
* Do not skip the Developer-options toggle: without it `flashing unlock` returns
  `FAILED (remote: 'OEM unlocking disabled')`.
* **Your data is gone after this.**  Take what you want off the tablet first.

* 如果 `flashing unlock` 被拒绝，说明该机型要走联想自己的解锁流程（厂商工具/应用，
  有时需要联想账号）—— 那不在本仓库范围内，请按 TB710FU 的资料操作。
* 别跳过开发者选项里的开关，否则会得到 `FAILED (remote: 'OEM unlocking disabled')`。
* **解锁会清空数据**，先把手里的东西备份出去。

## 2. A shell with `dd` / 一个带 `dd` 的 shell

Everything from `docs/INSTALL.md` §1 on runs from such a shell.  Two ways to get
one, in order of preference:

后面（`docs/INSTALL.md` 第 1 步起）所有命令都在这样的 shell 里跑。按推荐顺序有两种：

**(a) Boot a recovery image without flashing it / 临时启动一个 recovery 镜像**

```sh
fastboot boot twrp.img      # runs from RAM; nothing is written to flash
```

If that works, you get adb + a terminal and the flash stays untouched —
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

## 3. Back up the stock side / 先备份原厂侧

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
* If the numbers in `INSTALL.md` §1 are for the 256 GB variant and yours is a
  different size, recompute: `linboot` = 1 GiB = 262 144 sectors starting where
  the old partition table had room, and `userdata` gets **everything else** up to
  the last usable sector (total sectors − 34, since the backup GPT holds 33).
  `sgdisk --print /dev/sda` shows the usable range; do not guess.

* `persist` 与 `modem`/`fsg` 这组带的是单机校准数据，是最容易让人后悔没备份的。
* `sgdisk --backup` 让你可以用一条命令回到原厂分区表。
* Linux 侧**从不**碰 `boot_a`、`vendor_boot_a`、`dtbo_a`、`vbmeta*`，只写 `boot_b`、
  `linboot`、`linsys` 和 `misc` 标记 —— 所以原厂安卓可以继续与 Linux 并存启动。
* 如果 `INSTALL.md` 第 1 步里的数值是 256GB 版本的，而你的机器容量不同，请重算：
  `linboot` 取 1GiB（262 144 扇区）、起始位置接在原分区表有空间的地方，`userdata`
  拿**剩下的全部**（到最后一个可用扇区，即总扇区数 − 34，因为备份 GPT 占 33 个）。
  `sgdisk --print /dev/sda` 会显示可用范围，**不要猜**。

## 4. Now install / 开始安装

* partitions, boot chain, rootfs → **`docs/INSTALL.md`** §1–3
* first boot and what to expect → **`docs/INSTALL.md`** §3 (path A)
* going back to Android → **`docs/INSTALL.md`** §4
* if it does not boot → **`docs/INSTALL.md`** §5

## 5. Two honest notes / 两句实话

* **A locked bootloader cannot be restored.**  Unlocking is irreversible on this
  platform; "put it back to stock" means "flash stock images onto an unlocked
  device", which is fine, but the unlock marker stays.
  **无法把引导程序重新锁回去** —— 解锁在这类平台上是不可逆的；"恢复原厂"只能理解为
  "在已解锁设备上刷回原厂镜像"，解锁标记会一直保留。
* **Read `docs/KNOWN-ISSUES.md` before you commit your only tablet to this.**  The
  port works, but the speaker sound is distorted, WiFi is slow (and can take the
  machine down), and suspend has never been tried.  `docs/STATUS.md` has the
  per-subsystem picture.
  **如果这是你唯一的平板，动手前先读 `docs/KNOWN-ISSUES.md`。** 移植可用，但扬声器
  声音很炸、WiFi 慢（且可能把机器搞死）、suspend 从未试过。各部位情况见
  `docs/STATUS.md`。
