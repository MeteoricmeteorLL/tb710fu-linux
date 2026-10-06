# TB710FU firmware / 固件包

The device-specific firmware this port needs, captured from the running device on
**2026-10-05** and verified `md5sum -c` against the device's own
`/lib/firmware` — the 29 files below are byte-identical to what the machine in
front of us is running right now.

这个移植需要的设备专用固件，采集自 **2026-10-05** 的运行中系统，并与设备自身的
`/lib/firmware` 做过 `md5sum -c` 核对 —— 下面 29 个文件与实机在跑的完全一致。

## Install / 安装

```sh
tar xzf tb710fu-firmware-20261005.tar.gz -C /     # paths are lib/firmware/...
cd / && md5sum -c /path/to/MD5SUMS                # verify after unpacking
```

`MD5SUMS` uses `lib/firmware/...` paths, so run it from `/`.  The same files are
also inside `board/board-root.tgz` (with the kernel modules and board config) and
inside the shipped rootfs.

`MD5SUMS` 里的路径是 `lib/firmware/...`，所以要在 `/` 下执行校验。同一批文件也在
`board/board-root.tgz`（连同内核模块与板级配置）和随附的 rootfs 里。

## What is in it / 内容

| path | size | what / 作用 |
|---|---|---|
| `qcom/sm8650/xiaoxin/gt/gen70900_{sqe.fw,aqe.fw,zap.mbn}`, `gmu_gen70900.bin` | 85 K / 33 K / 12 K / 79 K | Adreno 750 GPU — **without these the panel stays black** / 没有它面板不亮 |
| `qcom/sm8650/xiaoxin/gt/{adsp,cdsp}.mbn` + `_dtb.mbn` + `*r.jsn` | 34.8 M / 5.9 M | ADSP + CDSP (audio DSP, sensors) and their remoteproc descriptions |
| `qcom/sm8650/xiaoxin/gt/vpu33_4v.mbn` | 2.3 M | Iris VPU (video decode/encode) |
| `qcom/sm8650/xiaoxin/gt/battmgr.jsn` | ~0.5 K | battery manager (ADSP) |
| `ath12k/WCN7850/hw2.0/{amss,board-2,m3}.bin` | 6.1 M / 2.3 M / 300 K | WCN7850 WiFi: firmware, board data (BDF), M3 — **in use** / 当前在用 |
| `ath12k/WCN7850/hw2.0/amss.bin.{stock,community}`, `board-2.bin.community`, `m3.bin.community` | — | the vendor-stock copy and the community variants, kept for comparison / 原厂副本与社区备选，留作对比 |
| `qca/hmtbtfw20.tlv`, `qca/hmtnv20.bin` | 274 K / 9.6 K | Bluetooth (HMT = WCN7850) firmware and NVM |
| `novatek/novatek_nt36532_fw.bin` | 246 K | touch controller firmware, flashed by the driver at probe / 触摸固件，驱动探测时烧录 |
| `aw882xx_acf.bin`, `awinic/aw88461_tb710fu.bin` | 3.5 K | the four AW882xx amplifier parameters (identical bytes) / 功放参数 |
| `Lenovo-TB710FU-tplg.bin`, `qcom/sm8650/Lenovo-TB710FU-tplg.bin`, `tplg/Lenovo-TB710FU-tplg.bin` | 17 K | ALSA topology (the kernel looks in `qcom/sm8650/`; the other two are copies the ALSA UCM and older revisions want) / ALSA 拓扑 |

Firmware must match the kernel build that loads it: `qcom_battmgr`, `aw882xx`,
`nvt_36xxx`, `ath12k` and the audio stack in `board/board-root.tgz` are the
matching modules.

固件与加载它的内核必须配套：`board/board-root.tgz` 里的 `qcom_battmgr`、`aw882xx`、
`nvt_36xxx`、`ath12k` 与音频栈就是与这批固件对应的模块。

## Where it came from, and the licence / 来源与授权

These are **proprietary vendor blobs**, extracted from this device's own
partitions (they are not ours to license, and Qualcomm/Lenovo do not distribute
them).  The set, and the panel/touch bring-up references that go with it, come
from **[SpendyYT](https://github.com/SpendyYT)** —
credit that author when you pass these on.

If you need a clean licensing story, do not redistribute this archive: use
`board/README-board-root.md` (which lists every blob with size and md5) as an
inventory and pull the files from your own stock firmware instead.

这些是**厂商私有 blob**，从本机分区里提取（不归我们授权，高通/联想也没有公开分发）。
这批固件以及配套的面板/触摸点亮参考来自
**[SpendyYT](https://github.com/SpendyYT)**，
转手时请注明该作者。

如果你需要一份授权干净的方案，就不要分发这个归档：用
`board/README-board-root.md`（列出每个 blob 的大小与 md5）当清单，改从自己的原厂固件
里取文件。

Note also that `kernel/Image.gz` has the GPU firmware built into it
(`CONFIG_EXTRA_FIRMWARE`), so that binary carries the same caveat.
另外 `kernel/Image.gz` 里内建了 GPU 固件（`CONFIG_EXTRA_FIRMWARE`），所以那个二进制
也带着同样的注意事项。
