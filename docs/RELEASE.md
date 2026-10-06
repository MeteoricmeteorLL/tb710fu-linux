# Publishing this / 发布说明

Everything here was produced on the device and verified on it; the one thing that
matters for a stranger downloading it is that the rootfs tarball is intact, and
that is what most of the checking below is about.

这里的产物都是在设备上生成并在设备上验证过的。对下载者最重要的一点是 rootfs
包必须完好无损，下面大部分校验都是为它服务的。

## 1. What goes where / 什么放哪里

**In the repository** (all small enough for git):

`README.md`, `docs/`, `scripts/`, `tools/`, `kernel/` (patches, sources, config,
`Image.gz` 15 MB, DTB), `uboot/` (patches, `config`, both `boot_b` images,
`u-boot-13r-src-*.tar.gz` 78 MB), `board/` (`stage-overrides/`, `board-root.tgz`
42 MB), `firmware/` (`tb710fu-firmware-*.tar.gz` 37 MB + `MD5SUMS` + `README.md`),
`release/` (checksums + manifest only).

**As a GitHub release asset** (2 GiB per-file limit — the tarball is 1.90 GiB, so
it fits, but it does not belong in git):

| asset | size | sha256 |
|---|---|---|
| `tb710fu-rootfs-20261006.tar.zst` | 2 043 329 593 | `a1325d30e5b3f70c070895efc7f543d3656bbd5b594894c06f36c0612355d442` |

If a host rejects the size, split it and document it:

```sh
split -b 1000M tb710fu-rootfs-20261006.tar.zst tb710fu-rootfs-20261006.tar.zst.part-
cat tb710fu-rootfs-20261006.tar.zst.part-* | sha256sum    # must match the line above
```

## 2. Sizes and hashes / 大小与哈希

`release/SHA256SUMS` (full list; regenerate with `sha256sum` over the paths in it):

| file | size | sha256 (first 16) |
|---|---|---|
| `release/linboot-20261006.img` | 33 554 432 | `05744e9a4fc849bc` |
| `uboot/boot_b-linboot-v3.img` | 614 800 | `c8465961ca0a0e65` |
| `uboot/boot_b-linboot-v3-fbreg.img` | 614 974 | `515e24c567ef937c` |
| `kernel/Image.gz` | 15 551 018 | `1847389c01cde501` |
| `kernel/dtb/dtb-20261006-fb-reserve.bin` | 146 158 | `f9d3d6d48ba41233` |
| `kernel/dtb/dtb-before-fix.bin` | 163 840 | `14e1ac68d780f37d` |
| `kernel/patches/TB710FU-full-tree.diff` | 178 824 | `2f369ff2807f37dd` |
| `board/board-root.tgz` | 41 824 487 | `0d366cbf6b0abb87` |
| `firmware/tb710fu-firmware-20261005.tar.gz` | 36 899 265 | `b01f91de0544` |
| `firmware/MD5SUMS` | 2 306 | `ac5c0dbc9798` |
| `uboot/u-boot-13r-src-20261006-fbreg.tar.gz` | 78 245 248 | `5ca72394b4b0efa3` |
| `tb710fu-rootfs-20261006.tar.zst` | 2 043 329 593 | `a1325d30e5b3f70c` |

`release/tb710fu-rootfs-20261006.manifest.md5` is the per-file md5 of all
75 175 files inside the tarball, and `release/CHECKSUMS.txt` is the record the
build wrote when it finished.

## 3. What was removed from the image, and how that was checked / 镜像里删了什么、怎么验证的

The rootfs is a **copy** of the running system (the live machine is untouched),
with these left out:

| left out | why |
|---|---|
| `/etc/wpa_supplicant-tb.conf`, `/etc/tb-wifi-credentials.conf` | they held the real SSID and PSK; the image ships templates and a first-boot file |
| the SSID/PSK in `/usr/local/bin/tb-wifi-up.sh` | rewritten to read `/etc/tb-wifi-credentials.conf` |
| `/var/lib/bluetooth/` | pairings and link keys are per-device |
| `/root/.config/chromium`, `/root/.config/falkon`, `/root/.mozilla`, `/root/.cache` | browsing history, cookies, saved logins |
| `/root/.ssh`, `/etc/ssh/ssh_host_*`, `/var/lib/fwupd/pki/` | private keys: host keys must be per-deployment, fwupd's local signing key is per-machine |
| `/root/.bash_history`, `.*history`, KDE state (`baloo`, `kwalletd`, `klipper`, `konsole`, `kactivitymanagerd`), `.local/share/Trash`, recently-used | what the user did |
| `/var/log`, `/root/*.log`, `/var/lib/NetworkManager`, `system-connections` | logs and leases carry the network name |
| `/etc/machine-id`, `/var/lib/dbus/machine-id`, `/var/lib/systemd/random-seed` | identify the machine the image came from |
| `/root/Desktop|Documents|Downloads|Files|Pictures`, `/var/lib/apt/lists`, `/var/cache`, `/usr/share/doc|man`, `/snap` | personal files and bulk that does not belong in an image |

`tb-firstboot.service` regenerates machine-id, ssh host keys and hostname on the
first boot of a deployment (`board/stage-overrides/`).

The build script proves the removal three ways rather than trusting the exclude
list: it greps the staged tree for the live SSID and PSK (and fails if either
appears), rejects any private key outside the distro's own trees, and then greps
the **compressed artifact's decompressed stream** for the same secrets.  From the
run that produced this tarball:

```
[13:34:48]     clean                                   <- stage: no secret, no stray key
[13:35:35]     75175 files, identical across both reads
[13:36:46]     secret scan clean                       <- artifact: none of the live secrets
```

## 4. Firmware: published, with its provenance / 固件：已发布，并注明来源

`board/board-root.tgz`, `firmware/tb710fu-firmware-20261005.tar.gz` and the
shipped rootfs all contain the **vendor firmware**: Qualcomm ADSP/CDSP/GPU
(`qcom/sm8650/xiaoxin/gt/*`), the WLAN BDF and firmware
(`ath12k/WCN7850/hw2.0/*`), the Novatek touch firmware and the AW882xx
parameters.  These are proprietary blobs extracted from this device's own
partitions, published here **deliberately** so that the port is usable out of the
box.  The 29-file set was verified with `md5sum -c` against the live device's
`/lib/firmware`, so it is exactly what the port was developed and tested on.

The set, and the panel/touch references that go with it, come from
**[SpendyYT/linux-firmware-tb710fu](https://github.com/SpendyYT/linux-firmware-tb710fu)**
— credit that author when you pass these on.  / 固件集与面板/触摸参考来自该作者，
转手或再分发时请一并注明。

If someone downstream needs a clean licensing story, point them at
`board/README-board-root.md` (every blob with size and md5) and
`firmware/MD5SUMS`: they can pull the same files from their own stock firmware.
`firmware/README.md` says all of this in one place.

One more place the blobs hide: `kernel/Image.gz` has the GPU firmware **built
into it** (`CONFIG_EXTRA_FIRMWARE`), which is deliberate — the panel needs it
before the rootfs is even mounted.  If you want a blob-free kernel, clear
`CONFIG_EXTRA_FIRMWARE`, rebuild, and put those files under `/lib/firmware` on the
device instead. / 还有一处：`kernel/Image.gz` 里**内建了 GPU 固件**
（`CONFIG_EXTRA_FIRMWARE`，为了让面板在 rootfs 挂载前就亮）。若想要不含 blob 的
内核，清掉该配置重编，把这些文件改为放到板上的 `/lib/firmware`。

**不要发布第三方 recovery（TWRP）的文件**：本仓库不含、也不托管任何 recovery 镜像，
`docs/DEPLOY.md` 只说"自行准备"。  / Do not publish third-party recovery (TWRP)
images — none are included here, and the deployment guide tells the reader to
obtain their own.

Everything else is: scripts/tools **MIT**, documentation **CC BY-SA 4.0**, kernel
and U-Boot changes under their upstream licences (GPL-2.0).

## 5. Pushing it / 推送步骤

There is no `gh` CLI and no stored git credentials on this machine, so the repo is
prepared here and pushed from where your credentials are:

```sh
cd opensource/tb710fu-linux

# 1. a repository of its own (this directory is the tree; it is not a git repo yet)
git init -b main
git add .
git commit -m "TB710FU mainline Linux: kernel patches, U-Boot, board files, docs"
git remote add origin git@github.com:<you>/tb710fu-linux.git
git push -u origin main

# 2. the big asset goes on the releases page, not in git
#    github.com/<you>/tb710fu-linux/releases/new
#    - tag:    rootfs-20261006
#    - title:  TB710FU rootfs 20261006 (Ubuntu 26.04, Plasma 6)
#    - attach: tb710fu-rootfs-20261006.tar.zst, CHECKSUMS.txt,
#              tb710fu-rootfs-20261006.manifest.md5
```

Notes / 注意:

* GitHub refuses files over 100 MB inside a git repository, and warns above
  50 MB.  Everything in this tree is under 100 MB, so `git add .` works:
  `board/board-root.tgz` 42 MB, `firmware/tb710fu-firmware-*.tar.gz` 37 MB,
  `uboot/u-boot-13r-src-*.tar.gz` 78 MB (that one will draw the 50 MB warning —
  the release page or git-lfs is tidier for it).  Only the 2 GB rootfs tarball
  **must** go on the release page.
* The tarball copy used for the release is
  `release-incoming/tb710fu-rootfs-20261006.tar.zst` in the project workspace
  (its sha256 was verified against the device's own record after transfer).
* Keep `release/CHECKSUMS.txt` and the manifest **next to** the tarball on the
  release page — that is what lets a downloader check it.

## 6. What is verified, and what is not / 已验证与未验证

Verified on this device / 本机已验证:

* the rootfs tarball: `zstd -t` passes, its decoded stream hashes the same on two
  reads with the page cache dropped in between, and `tar -d` compared every
  packed file against the staged tree file by file; sha256 after transfer to the
  PC matches the device's record;
* the DTB fix: the probe that caught three overwritten pages before the fix
  reports zero after it, and a 4 GiB write now hashes the same from the source,
  from the page cache and from disk (`KNOWN-ISSUES.md` §1);
* the shipped `linboot` is the image the device is running (its kernel window is
  byte-identical to `kernel/Image.gz`, its DTB window to the fixed DTB).

Not verified / 未验证:

* `boot_b-linboot-v3-fbreg.img` **compiles and packs** but has not been flashed
  here — the shipped DTB already neutralises that bug, so flashing it is optional;
* the audio path (speakers) has no verified working configuration — see
  `KNOWN-ISSUES.md` §3;
* WiFi throughput/latency, Bluetooth audio end to end, and the cause of the
  remaining random reboots (`KNOWN-ISSUES.md` §4.5) are all still open;
* nothing about Android beyond "it boots from `boot_a` and reformats
  `userdata` on its first boot".
