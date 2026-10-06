# Bringing up a different root filesystem / 部署其他 rootfs

The initramfs in this image does not care which distribution it finds: it looks
for the GPT partition named `linsys`, mounts it read-write as ext4, and if
`/etc/os-release` is there it uses it as the real root (`switch_root`) and mounts
`linboot` at `/boot`.  If that file is missing it falls back to the legacy
squashfs+overlay path, so a half-written rootfs fails safe.

镜像里的 initramfs 不关心你装的是哪个发行版：它按 GPT 分区名 `linsys` 找到分区、
以 ext4 读写挂载，只要里面 `/etc/os-release` 存在就当真实根（`switch_root`），并把
`linboot` 挂到 `/boot`；没有那个文件就回落到旧的 squashfs+overlay 路径，所以写坏的
rootfs 不会变砖。

That means “deploy another distro” is: **mkfs, extract, add the board bits below** — the
commands for that are in `docs/INSTALL.md` §3B; this document is what such a system
has to provide, and what cannot work on this port at all.

所以“换个发行版”就是：**格式化、解包、补上下面这些板级内容** —— 具体命令在
`docs/INSTALL.md` 第 3B 节；本文讲的是这样一个系统必须提供什么，以及哪些东西在本移植上
根本做不到。

---

## 1. The minimum / 最低要求

```sh
# from a recovery shell or the rescue console
mkfs.ext4 -L linsys /dev/block/by-name/linsys
mount /dev/block/by-name/linsys /mnt
# e.g. an Ubuntu/Debian base or cloud image, or a distro bootstrap
tar --xattrs --numeric-owner -xpf /path/to/other-rootfs.tar -C /mnt
```

Then make sure the new system has the kernel side of this port:

1. **Modules matching the kernel** — `/lib/modules/$(uname -r)` must match the
   kernel you boot.  Either rebuild the kernel inside the new rootfs, or copy the
   `7.2.0-gcf72cbb39da8-dirty` tree from this image
   (`board/modules/` in this repo) and run `depmod -a`.
   The modules that matter are the WiFi (`ath12k`/`mac80211`), the touch
   driver (`nvt_36xxx`, out-of-tree), the audio stack (q6*/snd-soc-*,
   `snd-soc-aw882xx`), `pwrseq-qcom-wcn`, `qcom_battmgr`, `mhi` and `apr`.
2. **Firmware** — unpack `firmware/tb710fu-firmware-20261005.tar.gz` at `/` and
   verify it (`cd / && md5sum -c <path>/MD5SUMS`).  That is the device-specific
   set (29 files, `md5sum -c`-verified against the live device) and it covers:
   GPU (`gen70900_*`, `gmu_gen70900.bin`), ADSP/CDSP (`qcom/sm8650/xiaoxin/gt/*`),
   touch (`novatek/novatek_nt36532_fw.bin`), audio (`aw882xx_acf.bin`,
   `Lenovo-TB710FU-tplg.bin`), WiFi (`ath12k/WCN7850/hw2.0/*`, `qca/hmt*`).
   `firmware/README.md` describes each file; `board/README-board-root.md` §3 has
   the same inventory with sizes and md5s.  Without the GPU firmware the panel
   stays black; without the touch firmware the digitizer never answers.
3. **The panel needs nothing from userspace** — the DRM driver is built into the
   kernel, and the device tree is in the `linboot` slot.
4. **A few configs** — unpack `board/board-root.tgz` (it holds `lib/firmware`,
   `lib/modules`, `etc`, `usr`, `klogd.sh`; extracting it at `/` deploys the whole
   set) and take at least these from it:
   * `/etc/modprobe.d/ath12k-override.conf` — **required** for WiFi (it forces
     the BDF entry name);
   * `/etc/modprobe.d/cfg80211-regdom.conf` — `ieee80211_regdom=CN`, without it
     5 GHz is passive-scan only;
   * `/etc/NetworkManager/conf.d/99-tb-wifi-unmanaged.conf` — hand `wlp1s0` to
     the WiFi service instead of NM;
   * `/etc/NetworkManager/conf.d/99-nodns.conf` — stop NM from emptying
     `/etc/resolv.conf`;
   * `/usr/share/udhcpc/default.script` — the fixed busybox DHCP script (it uses
     `$mask`, not `$subnet`);
   * `/etc/tmpfiles.d/tb-x11.conf` — recreates `/tmp/.X11-unix` (tmpfs) so
     XWayland works;
   * `/etc/systemd/system/upower.service.d/override.conf` and the PipeWire user
     units — the session runs as **root**, and both hard-code
     `ConditionUser=!root`.
5. **Services worth taking** (in `board-root/etc/systemd/system/` inside that
tarball):
   `tb-panel-cycle.service` (works around the panel latch race),
   `tb-console-quiet.service` (stops the kernel console fighting the compositor),
   `tb-touch-rebind.service` (re-probes the touch controller after the panel
   reset), `tb-audio-init.service`, `tb-wifi.service` + kick/watchdog,
   `tb-timesync.service`, plus `/usr/local/bin/tb-*` scripts and the
   `chromium`/`falkon` wrappers.

## 2. What the board-specific scripts assume / 板级脚本的假设

* serial console on the panel via `console=tbfb` (the kernel draws the boot log
  into the framebuffer at `0xD5100000` — see `KNOWN-ISSUES.md` §1, and make sure
  your DTB reserves it);
* the USB NCM gadget gives the rescue console at `192.168.7.2`; that link is what
  you use when there is no network and no display;
* `tb-*` scripts assume `busybox` (udhcpc), `iw`, `wpa_supplicant`, `rfkill`;
* the root account exists and can log in (`root` is the auto-login user in the
  shipped SDDM config — change the password after the first boot).

## 3. Other rootfs types that will *not* work / 不能用的类型

* **Anything requiring user namespaces** — `snapd`, `flatpak`, some sandboxes —
  because `CLONE_NEWUSER` returns `EPERM` on this port even for root
  (`KNOWN-ISSUES.md` §5).  Do not build a system that depends on them.
* **Systems without an ext4 root** — the initramfs only tries ext4 on `linsys`
  (a btrfs/f2fs/xfs root would need the initramfs patched; `tools/patch-init-linsys.py`
  is where that block lives, and it is a small shell edit).
* **32-bit userland** — the kernel is arm64-only with the vendor's 4 KiB
  page size, and the firmware binaries are 64-bit.

## 4. A quick checklist / 快速检查表

```sh
# after the first boot of a new rootfs
uname -r                                  # the kernel you shipped in linboot
cat /proc/device-tree/model               # Lenovo Xiaoxin Pad Pro GT (TB710FU)
ls /dev/dri/card0 && cat /sys/class/drm/card0-*/status    # "connected"
lsmod | grep -c nvt_36xxx                 # touch driver loaded
dmesg | grep -i 'reserved mem.*framebuffer'   # the fix from KNOWN-ISSUES §1 is in
aplay -l                                   # a card should exist (no sound yet, §3)
ip -br link | grep wlp1s0                  # WiFi device present after ~110 s
```
