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
> progress: WiFi is slow (and can crash the machine), the speakers play but
> sound badly distorted, and there is one serious
> memory-corruption bug whose root cause was found and whose fix is included
> here.  Everything is documented with the evidence that established it.
>
> **请先读 `docs/KNOWN-ISSUES.md`。** 移植可用但仍是进行中的工作：WiFi 慢（且可能把
> 机器搞死）、扬声器能出声但声音很炸，还有一个严重的内存损坏问题 —— 根因已找到，修复也在这个仓库里。每条都附了
> 得出结论的实测依据。

**Published / 已发布**: this repository ·
[rootfs release `rootfs-20261006`](https://github.com/MeteoricmeteorLL/tb710fu-linux/releases/tag/rootfs-20261006)
(the 2 GB tarball, sha256 `a1325d30…`) ·
U-Boot changes in [Uboot-For-TB710FU](https://github.com/MeteoricmeteorLL/Uboot-For-TB710FU)
commit `2c9e8827`, release [`fbreg-20261006`](https://github.com/MeteoricmeteorLL/Uboot-For-TB710FU/releases/tag/fbreg-20261006).

---

## What works / 可用状态

A working Linux tablet, with a few loud gaps: it boots, the panel and touch work,
the GPU is stable, USB and storage are solid — but WiFi is slow and can take the
machine down, **the speakers play with badly distorted sound**, and
suspend/sensors/camera have not been touched.

一台能用的 Linux 平板，但也有几个明显的缺口：能启动、屏幕与触摸可用、GPU 稳定、
USB 与存储可靠 —— 但 WiFi 慢且可能把机器搞死、**扬声器能出声但声音很炸**，
suspend/传感器/相机完全没做。

| | Status / 状态 |
|---|---|
| Boot chain, kernel, panel, touch, GPU, video codec, USB-NCM rescue link, storage | **works** / 可用 |
| Plasma 6 Wayland desktop, Chinese UI, root auto-login, virtual keyboard, Chromium/VLC | **works** / 可用 |
| WiFi (WCN7850 / ath12k) | **partial, and a crash hazard** — associates and DHCPs, poor latency/throughput, and the driver has hung this board (loaded on demand because of it: `KNOWN-ISSUES.md` §2) / 能连能拿地址但延迟吞吐差；**且驱动把本机搞死过**（因此按需加载，见 §2） |
| Speaker output | **works, badly distorted** — crackling/clipping at any volume / 能出声但很炸（严重失真） |
| Microphone | **untested** / 未验证 |
| Bluetooth | transport up; **audio tested with headphones only** / 传输层可用；音频只测过耳机 |
| Sensors, camera | **not started** / 未做 · **suspend** untested / 未验证 |
| `snap` / `flatpak` | **impossible** — `CLONE_NEWUSER` returns `EPERM` / 不可能 |
| Stability | the memory-corruption crash is fixed; random reboots still open / 内存损坏已修，随机重启仍未定位 |

Per-subsystem detail, with what was verified on the device and what was not:
**`docs/STATUS.md`**. / 每个部位的详细状态（哪些在实机验证过、哪些没有）见
`docs/STATUS.md`。

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
docs/                       (9 documents / 共 9 篇)
  INSTALL-FROM-ZERO.md  stock tablet → Linux: unlock, recovery shell, backups
  INSTALL.md         install this rootfs, or another distro / 安装教程（两条路径）
  STATUS.md          what works, part by part / 各部位支持情况
  DEPLOY.md          partitioning, boot chain, first boot, Android / 部署细节
  KNOWN-ISSUES.md    WiFi, speakers, stability, the memory bug / 已知问题全表
  ROOTFS.md          what a foreign rootfs must provide / 换 rootfs 的要求
  BUILD-KERNEL.md    rebuild the kernel / 重建内核
  BUILD-UBOOT.md     rebuild U-Boot / 重建 U-Boot
  RELEASE.md         publishing, checksums, licensing / 发布与授权
kernel/
  patches/           TB710FU-full-tree.diff (49 files) + base commit / 补丁与基线
  sources/           new files the diff does not carry / diff 里没有的新增源码
  config             the .config of the shipped kernel
  Image.gz           the kernel inside the linboot image
  dtb/               the fixed device tree blob, and the one from before the fix
uboot/
  patches/           the uart14fix lineage patches, incl. the byte-swap fix
  config, boot_b-linboot-v3{,-fbreg}.img, u-boot-13r-src-*.tar.gz
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
release/             SHA256SUMS, CHECKSUMS.txt, manifest, linboot image
LICENSE, .gitattributes
```

## Quick start / 快速开始

* **Start from a stock tablet** — `docs/INSTALL-FROM-ZERO.md`: unlock, get a
  recovery shell, back up the stock partitions. / 从原厂机器开始看
  `docs/INSTALL-FROM-ZERO.md`（解锁、拿 shell、先备份）。
* **Install it** — `docs/INSTALL.md`: partitions → U-Boot → `linboot` → rootfs,
  for this image **and** for another distribution. / 安装看 `docs/INSTALL.md`
  （本镜像与其他发行版两条路径）。
* **See what actually works** — `docs/STATUS.md`. / 可用性看 `docs/STATUS.md`。
* **Understand the rough edges** — `docs/KNOWN-ISSUES.md`. / 细节看
  `docs/KNOWN-ISSUES.md`。
* **Rebuild anything** — `docs/BUILD-KERNEL.md`, `docs/BUILD-UBOOT.md`. /
  重建看这两篇。
* **Publish/fork it** — `docs/RELEASE.md`. / 发布看 `docs/RELEASE.md`。

## Lineage and credits / 来源与致谢

* Linux **7.2.0** mainline, base commit
  `cf72cbb39da84b6f02f90c07f33b102fc10b16f0`, plus 49 modified files and a
  handful of new drivers (panel, touch, regulator, audio codec, board DTS).
* **Panel/touch bring-up and the firmware set for this device come from
  [SpendyYT/linux-firmware-tb710fu](https://github.com/SpendyYT/linux-firmware-tb710fu).
  Many thanks to that author — without that work this port would not have got a
  picture, a working digitizer, or the right blobs to hand the WCN7850 and the
  ADSP.**
* U-Boot from the **DanDrewCJ / u-boot-13r** lineage, with the `uart14fix`
  variant (Bluetooth UART left enabled) and the `linboot` boot contract; the
  device-tree byte-swap bug and the `memboot` re-targeting are patched here.
* Firmware blobs are the vendor's (extracted from the device's own partitions).
  They are in `firmware/` (29 files, `md5sum -c`-verified against the live
  device), in `board/board-root.tgz` and inside the rootfs.  `firmware/README.md`
  lists what each blob is for and where it came from; the licence situation and
  the "I need a clean licence" path are in `docs/RELEASE.md` §4. / 固件是厂商的
  （从设备自身分区提取）：在 `firmware/`（29 个文件，与实机逐文件 md5 核对过）、
  `board/board-root.tgz` 和 rootfs 里都有，每个文件的用途与来源见
  `firmware/README.md`，授权情况与"需要干净授权"的做法见 `docs/RELEASE.md` 第 4 节。

**面板/触摸的点亮工作与这台机器的固件集来自
[SpendyYT/linux-firmware-tb710fu](https://github.com/SpendyYT/linux-firmware-tb710fu)，
非常感谢这位作者** —— 没有那份工作，这个移植不会有点亮的屏、可用的触摸，也拿不到
交给 WCN7850 和 ADSP 的正确固件。

Licensing / 授权 — see **`LICENSE`**: scripts and tools **MIT**; documentation
**CC BY-SA 4.0**; the kernel and U-Boot changes follow their upstream licences
(GPL-2.0); the vendor firmware is not ours to license. / 授权细则见 `LICENSE`：
脚本与工具 MIT，文档 CC BY-SA 4.0，内核与 U-Boot 改动遵循上游 GPL-2.0，厂商固件不归
我们授权。
