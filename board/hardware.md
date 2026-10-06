# The board / 硬件速查

Facts gathered while bringing this port up, in one place, because several of them
matter more than they look (the boot console's fixed address, the partition
geometry, the WiFi power rails).

The panel/touch bring-up and the firmware set for this device come from
**[SpendyYT](https://github.com/SpendyYT)**
— with thanks to that author.

移植过程中攒下的硬件事实汇总。其中几条是"承重"的：绘制控制台的固定地址、分区几何、
WiFi 供电轨。面板/触摸的点亮工作与这台机器的固件集来自
**[SpendyYT](https://github.com/SpendyYT)**，
感谢该作者。

## Device / 设备

| | |
|---|---|
| model | Lenovo Xiaoxin Pad Pro GT (TB710FU) — `Lenovo Xiaoxin Pad Pro GT (TB710FU)` in `/proc/device-tree/model` |
| SoC | Qualcomm **SM8650Q** ("pineapple"), chip id `0x43051401` — the kernel calls it `C520v2` |
| GPU | Adreno 750, `gen70900` (a7xx gen3) |
| RAM | 8 GB, 7 010 MB usable |
| storage | 256 GB UFS, `/dev/sda`, **4096-byte logical sectors**, 61 390 848 sectors (234.2 GiB) |

## Display / 显示

| | |
|---|---|
| panel | Novatek **NT36532**, 3200×2000, **dual DSI**, DSC |
| drivers | `panel-novatek-nt36532-wqhd.c` (community lineage) and `panel-nt36532-wqhd-dual-dsi-dsc.c` |
| backlight | `sy7758` (`drivers/video/backlight/`) |
| regulators | `aw3750x` / `aw37503` / `aw37504` (`drivers/regulator/aw3750x.c`) |
| **boot framebuffer** | **`0xD5100000`, 3200×2000, stride 3200, 32 bpp (25.6 MiB)** — the ABL splash buffer the kernel's boot console draws into; it must stay reserved *and mapped* (`docs/KNOWN-ISSUES.md` §1) |
| latches | the panel sometimes comes up lit but blank (a real DRM off/on cycle fixes it — `tb-panel-cycle`) |

## Touch / 触摸

| | |
|---|---|
| controller | **Novatek NT36532** over **SPI** (`spi0.0`), driver `nvt_36xxx` (out of tree, in `drivers/input/touchscreen/NT36XXX_SPI/`) |
| firmware | `/lib/firmware/novatek/novatek_nt36532_fw.bin`, flashed by the driver at probe |
| quirk | the panel's DSI reset makes the SPI probe fail (`-22`) on a cold boot; `tb-touch-rebind.service` re-binds `spi0.0` once the display pipeline is quiet |

## Audio / 音频 (see `docs/KNOWN-ISSUES.md` §3 — it plays, but the speakers are distorted)

| | |
|---|---|
| codec | WCD939x over SoundWire |
| amplifiers | **4× AW882xx** smart amps (`snd-soc-aw882xx`, in-tree here) |
| parameters | `/lib/firmware/aw882xx_acf.bin` (byte-identical to the vendor's) |
| topology | `Lenovo-TB710FU-tplg.bin` (ALSA UCM under `/usr/share/alsa/ucm2/Qualcomm/sm8650/`) |
| DSP | ADSP firmware at `/lib/firmware/qcom/sm8650/xiaoxin/gt/adsp.mbn` |

## WiFi / Bluetooth (WCN7850)

| | |
|---|---|
| WiFi | `ath12k` over **PCIe0**, Gen2 ×2, `17cb:1107`; `phy0` appears **~110 s after a cold boot** |
| firmware | `ath12k/WCN7850/hw2.0/{amss,board-2,m3}.bin`, forced entry name via `modprobe.d/ath12k-override.conf` |
| rails | 7 input rails 852 mV–1.8 V, `GPIO16` = WLAN_EN, RPMH clock 76.8 MHz — brought up by `pwrseq-qcom-wcn` |
| Bluetooth | over **`uart14`** (`hci_uart`), firmware `qca/hmtbtfw20.tlv` + `qca/hmtnv20.bin` — this is why the U-Boot build must be the **uart14fix** lineage |
| quirks | DHCP must request broadcast replies (`udhcpc -B`); regdomain must be set (`ieee80211_regdom=CN`); host TX is needed before RX is delivered (`tb-wifi-kick`) |

## Other hardware / 其他

| | |
|---|---|
| video | Iris VPU firmware `qcom/sm8650/xiaoxin/gt/vpu33_4v.mbn` |
| battery | `qcom_battmgr` (ADSP), needs `upower` with `PrivateUsers=no` under a root session |
| USB | device-mode **NCM** gadget → host `192.168.7.1`, board `192.168.7.2`; this is the rescue path |
| known warnings | UFS `vdd-hba`/`vccq2` regulator missing (harmless), four `pmic_arb` call traces (harmless) |

## Partition geometry / 分区几何（all in 4 KiB logical sectors / 全部为 4K 扇区）

| # | name | first | last | size |
|---|---|---|---|---|
| 14 | `linboot` | 5 105 064 | 5 367 207 | 1 GiB |
| 15 | `linsys` | 5 367 208 | 38 921 639 | 128 GiB |
| 16 | `userdata` | 38 921 640 | 61 390 842 | 85.71 GiB |

`linboot` is a raw slot, read by U-Boot at three fixed windows: kernel at 0
(16 MiB), initramfs at 16 MiB (8 MiB), DTB at 24 MiB (160 KiB).  See
`docs/BUILD-KERNEL.md` §4.
