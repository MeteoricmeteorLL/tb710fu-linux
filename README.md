# TB710FU mainline Linux / 联想小新 Pad Pro GT 主线 Linux 移植

Running mainline Linux and Plasma on the **Lenovo Xiaoxin Pad Pro GT
(TB710FU)** — Qualcomm **SM8650Q**, 8 GB RAM, 256 GB UFS, Adreno 750.

在**联想小新 Pad Pro GT（TB710FU）**上跑主线 Linux + Plasma —— 高通 **SM8650Q**，
8GB 内存，256GB UFS，Adreno 750。

This repository is the whole thing: the kernel patches, the U-Boot changes, the
board files, the scripts that build and deploy, and a ready-to-flash root
filesystem image.  Android still boots from the other slot; this lives in its own
partitions next to it.

这个仓库包含全部内容：内核补丁、U-Boot 改动、板级文件、构建与部署脚本，以及可以直接
刷入的根文件系统镜像。安卓仍可从另一个槽启动，Linux 有自己的独立分区。

> **Read `docs/KNOWN-ISSUES.md` first.**  The port works, but it is a work in
> progress: WiFi is slow, the speakers are silent, and there is one serious
> memory-corruption bug whose root cause was found and whose fix is included
> here.  Everything is documented with the evidence that established it.
>
> **请先读 `docs/KNOWN-ISSUES.md`。** 移植可用但仍是进行中的工作：WiFi 慢、扬声器
> 无声，还有一个严重的内存损坏问题 —— 根因已找到，修复也在这个仓库里。每条都附了
> 得出结论的实测依据。

---

## What works / 可用状态

| | Status / 状态 |
|---|---|
| Boot chain (ABL → U-Boot → kernel → rootfs) | **works** / 可用 |
| Plasma 6 Wayland desktop, Chinese UI, root auto-login | **works** / 可用 |
| Panel (NT36532 dual-DSI, 3200×2000) | **works**, with a latch-race workaround / 可用（有闩锁竞态绕过） |
| Touch (Novatek NT36532) | **works** (re-probe service) / 可用 |
| GPU (Adreno 750 / gen70900) | **works** (IFPC quirk removed) / 可用 |
| Battery reporting, backlight, virtual keyboard (maliit) | **works** / 可用 |
| Chromium / VLC / glxgears (XWayland) | **works** (wrappers in `/usr/local/bin`) / 可用 |
| WiFi (WCN7850 / ath12k) | **partial** — associates and DHCPs, poor latency/throughput / 能连能拿地址，延迟吞吐差 |
| Speakers / audio out | **not working** — no working playback path yet / 通路尚未打通 |
| Bluetooth | transport up, not verified end to end / 传输层起来了，未端到端验证 |
| `snap` / `flatpak` | **impossible** — `CLONE_NEWUSER` returns `EPERM` / 不可能 |
| Stability | improved; the memory-corruption crash is fixed, random reboots still open / 已改善，随机重启仍未定位 |

## The one thing to know / 最该知道的一件事

A 4 GiB file written on this board could come back with different contents than
were written — silently, and only for large files.  Root cause: the kernel's own
boot console, liveness gauge and black box draw into the bootloader's splash
framebuffer at a fixed physical address (`0xD5100000`, 25 MiB) plus two 1 MiB
black-box rings, and **none of those regions was reserved**; U-Boot's
reservation code writes the device-tree `reg` byte-swapped, so the kernel
reserved 36 KB at `0x10d5` instead of the real 25 MiB.  The page allocator
therefore handed those pages out as page cache, and the drawing code overwrote
whatever landed in them.

在这台机器上写 4GiB 文件可能写完就变样 —— 静默发生，而且只在大文件上出现。根因是
内核自绘的启动控制台/心跳仪/黑匣子在往 bootloader 开机动画的 framebuffer
（固定物理地址 `0xD5100000`，25MiB）和两个 1MiB 的黑匣子日志环里写，而**这些区间
都没有被保留**：U-Boot 的保留代码把设备树的 `reg` 写成了字节反序，内核于是只保留了
`0x10d5` 处的 36KB 而不是真正的 25MiB，页分配器把这块当普通内存发出去，绘制代码随即
改写了落在里面的页。

It is fixed by three `reserved-memory` nodes in the DTB
(`tools/fix-dtb-fb-reserve.py`, applied in the shipped `linboot` image), and the
full evidence chain — `/proc/self/pagemap` recovering the physical addresses,
pixel values appearing in our own pages while we watched — is written up in
`docs/KNOWN-ISSUES.md` §1.  Measured before/after on the same board:

修复方式是给 DTB 加三个 `reserved-memory` 节点（`tools/fix-dtb-fb-reserve.py`，已应用
在随附的 `linboot` 镜像里）。完整证据链（用 `/proc/self/pagemap` 反查物理地址、亲眼看
到自己页里出现像素值）写在 `docs/KNOWN-ISSUES.md` 第 1 节。同一台机器修复前后实测：

| 4 GiB write: md5 of source / page cache / disk | before | after |
|---|---|---|
| | cache ≠ source, 3 bad blocks | all three equal, 0 bad blocks |

## Repository layout / 仓库结构

```
docs/
  DEPLOY.md          from TWRP to a booting desktop / 从 TWRP 到桌面
  KNOWN-ISSUES.md    WiFi, speakers, stability, the memory bug / 已知问题全表
  ROOTFS.md          deploying a different distribution / 换其他 rootfs
  BUILD-KERNEL.md    rebuild the kernel / 重建内核
  BUILD-UBOOT.md     rebuild U-Boot / 重建 U-Boot
  RELEASE.md         what to publish, checksums, GitHub / 发布与上传
kernel/
  patches/           TB710FU-full-tree.diff + base commit / 补丁与基线
  sources/           new files the diff does not contain / diff 里没有的新增源码
  config             the .config of the shipped kernel
  Image.gz           the kernel inside the linboot image
  dtb/               the fixed device tree blob + how it was produced
uboot/
  patches/           the uart14fix lineage patches, incl. the byte-swap fix
  boot_b-linboot-v3.img
board/
  stage-overrides/   sanitized files the release image substitutes
  board-root.tgz     firmware + modules + configs + services (extract at /)
  README-board-root.md  the inventory: every blob, module and service, with md5s
  hardware.md        the board: panel, touch, codecs, power rails
firmware/
  tb710fu-firmware-*.tar.gz   the 29 device-specific blobs, verified against the
                              live device / 与实机逐文件核对过的 29 个固件
  MD5SUMS, README.md          what is inside, provenance, licence note
tools/               the surgical tools (GPT, DTB, U-Boot, initramfs, probes)
scripts/             make-release-rootfs.sh, verify-rootfs.sh
release/             the published assets and their checksums
```

## Quick start / 快速开始

* **Install it**: `docs/DEPLOY.md` — partitions, U-Boot, `linboot`, rootfs, first
  boot. / 安装看 `docs/DEPLOY.md`。
* **Understand the rough edges**: `docs/KNOWN-ISSUES.md`. / 细节看
  `docs/KNOWN-ISSUES.md`。
* **Rebuild anything**: `docs/BUILD-KERNEL.md`, `docs/BUILD-UBOOT.md`. /
  重建看这两篇。
* **Publish/fork it**: `docs/RELEASE.md`. / 发布看 `docs/RELEASE.md`。

## Lineage and credits / 来源与致谢

* Linux **7.2.0** mainline, base commit
  `cf72cbb39da84b6f02f90c07f33b102fc10b16f0`, plus 47 modified files and a
  handful of new drivers (panel, touch, regulator, audio codec, board DTS).
* **Panel/touch bring-up and the firmware set for this device come from
  [SpendyYT/linux-firmware-tb710fu](https://github.com/SpendyYT/linux-firmware-tb710fu).
  Many thanks to that author — without that work this port would not have got a
  picture, a working digitizer, or the right blobs to hand the WCN7850 and the
  ADSP.**
* U-Boot from the **DanDrewCJ / u-boot-13r** lineage, with the `uart14fix`
  variant (Bluetooth UART left enabled) and the `linboot` boot contract; the
  device-tree byte-swap bug and the `memboot` re-targeting are patched here.
* Firmware blobs are the vendor's (extracted from the device's own partitions)
  and are **published here on purpose**, so the port works out of the box: they
  are in `firmware/` (29 files, `md5sum -c`-verified against the live device),
  in `board/board-root.tgz` and inside the rootfs.  `firmware/README.md` lists
  what each blob is for and where it came from; `docs/RELEASE.md` §4 has the
  provenance and the "I need a clean licence" path. / 固件是厂商的（从设备自身分区
  提取），**这里是有意公开的**，好让移植开箱可用：在 `firmware/`（29 个文件，与实机
  逐文件 md5 核对过）、`board/board-root.tgz` 和 rootfs 里都有，来源与授权说明见
  `firmware/README.md` 与 `docs/RELEASE.md` 第 4 节。

**面板/触摸的点亮工作与这台机器的固件集来自
[SpendyYT/linux-firmware-tb710fu](https://github.com/SpendyYT/linux-firmware-tb710fu)，
非常感谢这位作者** —— 没有那份工作，这个移植不会有点亮的屏、可用的触摸，也拿不到
交给 WCN7850 和 ADSP 的正确固件。

Licensing / 授权: scripts and tools here are **MIT**; the documentation is
**CC BY-SA 4.0**; the kernel and U-Boot changes follow their upstream licences
(GPL-2.0).  Vendor firmware is not ours to license. / 脚本与工具 MIT，文档
CC BY-SA 4.0，内核与 U-Boot 改动遵循上游 GPL-2.0，厂商固件不归我们授权。
