# Deployment reference / 部署参考

From a recovery shell to a booting Plasma desktop.  Every command here was run on
the device; the numbers are for a 256 GB TB710FU with a 4096-byte-logical-sector
UFS (`/dev/sda`, 61 390 848 sectors of 4096 bytes = 234.2 GiB).

从 recovery shell 到能起 Plasma 桌面。下面每条命令都是在实机上跑过的；数值对应 256GB
TB710FU 的 UFS（逻辑扇区 4096 字节，`/dev/sda`，共 61 390 848 个扇区 = 234.2GiB）。

**Scope / 定位**: this is the *reference* — partition numbers, the reason for each
step, the way back to Android, and the failure table.  For a step-by-step
walkthrough start with `docs/INSTALL-FROM-ZERO.md` (stock device, nothing
partitioned yet) or `docs/INSTALL.md` (bootloader already unlocked; two install
paths).

本文是**参考文档**：分区数值、每一步的原因、回安卓的方法、故障排查表。要按步骤跟着做，
请看 `docs/INSTALL-FROM-ZERO.md`（原厂机器、分区未动）或 `docs/INSTALL.md`（已解锁，
两条安装路径）。

Read `docs/KNOWN-ISSUES.md` first — in particular the memory-corruption item, and
make sure the DTB you install carries the three `reserved-memory` nodes.

请先读 `docs/KNOWN-ISSUES.md`（尤其是内存损坏那一条），并确认你要装的 DTB 带上了
三个 `reserved-memory` 节点。

---

## 0. What ends up where / 最终布局

| Partition (GPT name) | Size | Contents / 内容 |
|---|---|---|
| `boot_a` | — | stock Android kernel — **do not touch** / 原厂安卓内核，别动 |
| `boot_b` | — | U-Boot (uart14fix lineage, patched to boot `linboot`) |
| `linboot` (sda14) | 1 GiB | raw slot: kernel@0, initramfs@16 MiB, DTB@24 MiB |
| `linsys` (sda15) | 128 GiB | the Linux root filesystem, ext4, label `linsys` |
| `userdata` (sda16) | rest | Android userdata (Android reformats it itself on first boot) |
| `recovery_a` | — | your own recovery (not shipped here / 你自己装的第三方 recovery，本仓库不提供) |
| `misc` | — | cleared so the slot logic boots slot B / 清空以让槽位逻辑走到 B |

Boot chain: `ABL → boot_b (U-Boot) → memboot from linboot (kernel + initramfs +
DTB) → initramfs mounts linsys and switch_roots → systemd → SDDM (root auto-login)
→ Plasma 6 Wayland`.  The initramfs also brings up a rescue console on USB NCM
(board `192.168.7.2`, host `192.168.7.1`, `nc 4444` / `telnet 4445`).

启动链：`ABL → boot_b (U-Boot) → 从 linboot 加载内核/initramfs/DTB → initramfs
挂 linsys 并 switch_root → systemd → SDDM（root 自动登录）→ Plasma 6 Wayland`。
initramfs 还会在 USB NCM 上开一个救援控制台（板 192.168.7.2 / 主机 192.168.7.1，
`nc 4444` / `telnet 4445`）。

## 1. Files you need / 需要的文件

* `release/linboot-<date>.img` — the 32 MiB raw slot (kernel + initramfs + DTB)
* `release/tb710fu-rootfs-<date>.tar.zst` — the root filesystem
* `uboot/boot_b-linboot-v3.img` — U-Boot for `boot_b`
* `release/CHECKSUMS.txt` — sha256/md5 of the tarball, and its per-file manifest
* a recovery that gives you a shell with `dd` and `adb` — **no recovery image is
  distributed with this repository**; get your own from wherever you trust (TWRP
  builds for this device exist in the community).  Take it from whoever publishes
  it, under their terms, not from here.  Flashing one overwrites `recovery_a`,
  which is why the DTB lives in `linboot` and not there.

Verify what you downloaded before flashing / 刷之前先校验:

```sh
sha256sum tb710fu-rootfs-20261006.tar.zst   # must match release/CHECKSUMS.txt
zstd -t tb710fu-rootfs-20261006.tar.zst     # "ok"
# optional, per file:  tar --zstd -xf ... --to-command ... (see scripts/verify-rootfs.sh)
```

## 2. Partitioning (only if you need a fresh layout) / 分区（仅在需要重划时做）

The device's `sgdisk` build **accepts long options only** (`--new=`, not `-n`),
and the UFS reports **4096-byte logical sectors**, so every number below is in
4 KiB sectors — check with `sgdisk --print /dev/sda` before you touch anything.
This is what the shipped table looks like:

这台设备上的 `sgdisk` **只认长选项**，而且 UFS 报的是 **4096 字节逻辑扇区**，
所以下面所有数字都是 4K 扇区 —— 动手前先用 `sgdisk --print /dev/sda` 核对。当前
在用的分区表是这样：

```sh
# in a recovery shell (e.g. TWRP), adb shell / terminal
sgdisk --print /dev/sda                       # note the current userdata type GUID
sgdisk --backup=/tmp/gpt-before.bin /dev/sda  # keep this file somewhere safe

sgdisk --delete=14 --delete=15 /dev/sda       # old userdata + linroot (this WIPES them)
sgdisk --new=14:5105064:5367207   --change-name=14:linboot  --typecode=14:8300 /dev/sda
sgdisk --new=15:5367208:38921639  --change-name=15:linsys   --typecode=15:8300 /dev/sda
sgdisk --new=16:38921640:61390842 --change-name=16:userdata --typecode=16:<original userdata GUID> /dev/sda

sgdisk --print /dev/sda                       # verify ranges and names
sgdisk --verify /dev/sda
```

* `linboot` = 1 GiB, `linsys` = 128 GiB, `userdata` = the remaining 85.7 GiB.
* Keep Android's original **type GUID** for `userdata` (from the `--print` you
  took first) — Android refuses to format it otherwise.  `8300` (Linux
  filesystem) is right for `linboot` and `linsys`.
* The kernel keeps its own view of the table: refresh it **per partition**, never
  with a blanket `partx -u` (that would re-read a partition someone has open):
  `partx -d --nr 14 /dev/sda; partx -a --nr 14 /dev/sda; partx -a --nr 16 /dev/sda`
* If anything does not match the numbers above, stop and restore with
  `sgdisk --load-backup=/tmp/gpt-before.bin /dev/sda`.

An alternative generator, which writes the header and both GPT copies itself and
self-checks the CRCs, is `tools/make-linsys-gpt.py` (produces `dd`-able blobs).

## 3. Flash U-Boot and the boot slot / 刷 U-Boot 与引导槽

```sh
# still in the recovery shell (adb shell)
dd if=/dev/block/by-name/boot_b of=/sdcard/boot_b-backup.img     # back up first
dd if=boot_b-linboot-v3.img of=/dev/block/by-name/boot_b bs=4096 conv=fsync
sync
md5sum /dev/block/by-name/boot_b    # compare with the image you wrote (first 614800 bytes)
```

`boot_a` keeps the stock Android kernel by design: switching back to Android is
a matter of setting the active slot again (§7).  Do **not** write U-Boot to
`boot_a`.

Alternatively from fastboot: `fastboot flash boot_b boot_b-linboot-v3.img`.

## 4. Write the boot slot image / 写入引导槽镜像

`linboot` is a raw 1 GiB slot with three fixed windows:

| offset | size | contents |
|---|---|---|
| `0x0000000` (0) | 16 MiB window | `Image.gz` (gzipped kernel) |
| `0x1000000` (16 MiB) | 8 MiB window | initramfs (TBIRD container) |
| `0x1800000` (24 MiB) | 160 KiB window | device tree blob |

```sh
dd if=linboot-20261006.img of=/dev/block/by-name/linboot bs=4096 conv=fsync
sync
# read it back and compare: the image is 32 MiB
dd if=/dev/block/by-name/linboot bs=4096 count=8192 of=/tmp/lb-readback.img
md5sum /tmp/lb-readback.img linboot-20261006.img
```

U-Boot reads exactly those windows (`blk_dread(start+0x1800, 0x28)` for the DTB),
so a DTB larger than 160 KiB is silently truncated — check with
`tools/fix-dtb-fb-reserve.py` output, which prints the size against that window.

To replace just the kernel or just the DTB, write only that window with
`dd ... bs=4096 seek=<blocks> conv=notrunc` (kernel: `seek=0`, DTB: `seek=6144`).
`tools/patch_uboot-linboot.py` documents the U-Boot side of this contract.

## 5. Create the root filesystem / 建立根文件系统

```sh
mkfs.ext4 -L linsys -m 1 /dev/block/by-name/linsys      # the GPT name AND the label matter
mkdir -p /mnt/linsys && mount /dev/block/by-name/linsys /mnt/linsys

cd /mnt/linsys
zstd -dc /path/to/tb710fu-rootfs-20261006.tar.zst | tar --xattrs --numeric-owner -xpf -
sync
```

* The initramfs looks for the partition **by GPT name `linsys`** and requires it
  to be ext4 with `/etc/os-release` inside; if that file is missing it falls back
  to the legacy squashfs path, so do not skip it.
* `--xattrs` keeps file capabilities (needed by e.g. `ping`, `passwd`); without
  it those binaries lose their capabilities.
* ~5.1 GiB extracted, 75 175 files.  On a UFS this takes a couple of minutes.

## 6. First boot / 首次启动

```sh
umount /mnt/linsys
# make sure the slot logic boots B (this is what the A/B scheme needs on this device)
dd if=/dev/zero of=/dev/block/by-name/misc bs=4096 count=1
sync
reboot            # or: hold power ~15 s, then power on cold
```

What you should see / 应该看到:

1. the U-Boot splash, then a dark screen while the kernel boots (~30–60 s);
2. the panel console briefly (kernel messages drawn on the framebuffer), then
   Plasma's SDDM login — root is auto-logged in, no password;
3. the network: the **USB NCM** link is up (`192.168.7.2`), so `ssh root@192.168.7.2`
   works with the password `tb710fu` (change it: `passwd`);
4. WiFi is **on demand** — put your network into
   `/etc/tb-wifi-credentials.conf` (`SSID=`, `PSK=`, then `chmod 600`) and run
   `systemctl start tb-wifi.service`.  First association after a cold boot takes
   ~110 s because `phy0` only appears then.  See `docs/KNOWN-ISSUES.md` for how
   bad the throughput/latency currently is.

On the very first boot `tb-firstboot.service` regenerates the machine-id, the ssh
host keys and the hostname; that is why they are absent from the image.

## 7. Going back to Android / 回到安卓

```sh
# from Linux
reboot bootloader          # or hold power ~15 s
# in fastboot
fastboot set_active a
fastboot erase misc
fastboot reboot            # then power the device on cold
```

Android reformats `userdata` on its first boot after this, so anything you left
in it is gone.  The Linux side (`linboot`, `linsys`) is untouched — `fastboot
set_active b` brings Linux back.

## 8. If it does not boot / 起不来怎么办

| Symptom | Cause | Fix |
|---|---|---|
| nothing at all, no U-Boot | `boot_b` write failed | re-flash U-Boot (§3); check with `md5sum` |
| U-Boot runs, kernel never gets there | DTB malformed / linboot window wrong | restore the previous DTB: `dd if=<backup> of=/dev/block/by-name/linboot bs=4096 seek=6144 conv=fsync` |
| backlight on, no picture | panel latch race | from the rescue console (or ssh): `/usr/local/bin/tb-panel-cycle`; the shipped `tb-panel-cycle.service` does this at every boot |
| text on screen, then black | compositor/console fight | `systemctl stop tb-console-quiet.service` to put kernel logs back on the panel |
| it boots, then freezes after a while | see `docs/KNOWN-ISSUES.md` §4 | check `/sys/fs/pstore` and the previous boot's lines on the panel |
| rescue console only (no rootfs) | `linsys` not ext4 / missing `/etc/os-release` | redo §5; the init falls back by design when that file is absent |

The rescue console is the thing to rely on: it is in the initramfs, on USB NCM,
independent of the root filesystem.  From there `/boot` is the `linboot`
partition, so you can replace the kernel or DTB without a PC-side flasher.

## 9. Redeploying a different root filesystem / 换用别的 rootfs

You do not have to use this Ubuntu image — anything with `/etc/os-release` works.
See `docs/ROOTFS.md` for what such a system must provide (kernel modules,
firmware, the board config, a few services) and how to bring it up.

不一定非用这个 Ubuntu 镜像，任何带 `/etc/os-release` 的系统都能跑。需要该系统提供
什么（内核模块、固件、板级配置、若干服务）见 `docs/ROOTFS.md`。
