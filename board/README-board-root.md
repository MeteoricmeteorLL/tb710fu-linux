# TB710FU（联想小新 Pad Pro GT / SM8650Q）固件与驱动重建包

> **固件与面板/触摸参考来源**：本包中的固件集与面板/触摸点亮参考来自
> **[SpendyYT/linux-firmware-tb710fu](https://github.com/SpendyYT/linux-firmware-tb710fu)**，
> 非常感谢该作者的帮助；再分发这些 blob 时请一并注明来源。
>
> 本文里的 `board-root/` 就是本仓库的 `board/board-root.tgz`（解包即得该目录；
> 单独要固件的话用 `firmware/tb710fu-firmware-20261005.tar.gz` + `firmware/MD5SUMS`）。
>
> 注意：本文是从原项目工作区原样带过来的清单文档，其中出现的 `PROJECT_STATE.md`、
> `checksums-*.md5`、`tools/verify-all.sh`、`kernel/recovery_b-*.bin` 等路径属于那个
> 工作区，本仓库并未包含；本仓库里对应的东西是 `release/`、`tools/`、`kernel/` 下的同名
> 或相似文件。

**采集时间**：2026-10-05 19:xx
**采集来源**：平板当前实际运行的系统（不是历史副本）——Ubuntu 26.04.1 LTS，内核
`7.2.0-gcf72cbb39da8-dirty #185`（2026-10-02 编译），root = squashfs 下层 + ext4 upper 的 overlay。

**用途**：重建系统（重装 rootfs / 重刷 boot 分区 / 换新 rootfs 发行版）之后，用本包把
**内核模块、固件、板端配置、systemd 服务**一次性恢复；同时保留**从源码重建内核**所需的
一切（补丁、新增源文件、.config、编译产物）。

包内 18 个关键文件的 md5 已与平板逐一对过，全部一致（见 `tools/deploy-to-board.ps1 -VerifyOnly` 输出）。

---

## 1. 快速恢复（重装系统后）

前提：平板在线——USB NCM 链路，板 `192.168.7.2`，主机 `192.168.7.1`，telnet shell 端口 `4445`。

```powershell
cd D:\zcodeproject\tb710fu\rebuild-kit

# 一键：推包 → 解包到 / → 补符号链接 → depmod → daemon-reload → enable 服务 → md5 校验
powershell -ExecutionPolicy Bypass -File tools/deploy-to-board.ps1

# 只校验（不改动板子）
powershell -ExecutionPolicy Bypass -File tools/deploy-to-board.ps1 -VerifyOnly
```

板端手工等价操作（如果不用上面的脚本，tar 包在 `deploy/board-root.tgz`）：

```sh
# 在板上
cd / && tar xzf /tmp/board-root.tgz
chmod +x /usr/local/bin/tb-* /usr/local/bin/wifi-on /usr/local/bin/fix-display /klogd.sh
depmod -a 7.2.0-gcf72cbb39da8-dirty
systemctl daemon-reload
for s in tb-audio-init tb-console-quiet tb-freeze-watch tb-keyd tb-panel-cycle \
         tb-stress-watch tb-touch-rebind tb-wifi-kick tb-wifi-regdom tb-wifi-unblock tb-wifi-watchdog; do
  systemctl enable $s.service
done
```

**推包方式**（`deploy/board-root.tgz`，41 MB）：`tools/deploy-to-board.ps1` 内置
board-listen-netcat 推送（与项目里已验证的 `tools/tb-push.ps1` 同一原语）；
也可以自己起 HTTP：主机 `python -m http.server 8000 --directory rebuild-kit/deploy`，
板上 `wget http://192.168.7.1:8000/board-root.tgz -O /tmp/board-root.tgz`。

> 从板端往主机拉文件用 `tools/tb-pull.ps1`，或在板上起
> `busybox httpd -p 8080 -h /tmp` 然后在主机 `curl -O http://192.168.7.2:8080/<file>`
> （41 MB 实测 40 秒左右；**不要用 telnet 通道传大文件，会卡死终端**）。

---

## 2. 目录结构

```
rebuild-kit/
├── board-root/                ← 板端落盘集：解包到 / 即完成部署（lib/ etc/ usr/ klogd.sh）
│   ├── lib/firmware/…         ← 全部自定义固件（按内核查找路径存放）
│   ├── lib/modules/7.2.0-gcf72cbb39da8-dirty/…  ← 全部自定义/重编模块（30 个 .ko）
│   ├── etc/…                  ← systemd 服务、modprobe.d、NM 配置、udhcpc 脚本
│   └── usr/…                  ← /usr/local/bin/tb-* 脚本、ALSA UCM
├── kernel/                    ← 内核与补丁
│   ├── Image.gz-fix3          ← 当前运行内核（md5 717f913b…）
│   ├── recovery_b-head-fix3.bin   ← recovery_b 分区头（内核+initramfs，15.4 MB）
│   ├── avb-fix3-recovery_b.img    ← 可整分区刷写的 AVB boot 镜像（104 MB）
│   ├── dtbs/                  ← 当前 DTB：onboard-dtb-real-20261003.dts（反编译）+ current-deployed-dtb.bin（/sys/firmware/fdt 导出）
│   ├── kernel-config          ← 当前内核 .config（从 /proc/config.gz 导出）
│   ├── initramfs/             ← initramfs 的 init（打过补丁版 + 原版）
│   └── patches/               ← TB710FU-full-tree.diff（47 文件）+ base commit + acm*.py 增量脚本 + BDF 工具
├── sources/
│   ├── kernel-tree/           ← 内核树“新增文件”源码（diff 不含它们，重建必须补上）
│   ├── out-of-tree-drivers/   ← aw882xx 独立驱动源码（archive/aw882xx）
│   └── build-scripts/         ← 原项目编译脚本（build-kernel.sh 等）
├── board-capture/             ← 板端运行时快照：kernel config、DTB、lsmod、dmesg、分区表、md5
├── tools/                     ← PC 侧工具（见第 8 节）
├── deploy/board-root.tgz      ← 部署载荷（board-root 的 tar.gz）
├── checksums-board-root.md5   ← board-root 全量 md5 清单（110 文件）
├── checksums-kernel-sources.md5
└── _board-dump/               ← 板端原始 tar 包（校验用）
```

---

## 3. 固件清单（`board-root/lib/firmware/`，部署后对应 `/lib/firmware/`）

### WiFi / 蓝牙（WCN7850，ath12k）
| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `ath12k/WCN7850/hw2.0/amss.bin` | 6,090,816 | `ee2f1a64…` | **当前在用**（原厂 stock 版，与社区版不同） |
| `ath12k/WCN7850/hw2.0/amss.bin.stock` | 6,090,816 | `ee2f1a64…` | 原厂副本（== 上面的 amss.bin） |
| `ath12k/WCN7850/hw2.0/amss.bin.community` | 7,458,880 | `81f39ee4…` | 社区版备选（历史上跑通过） |
| `ath12k/WCN7850/hw2.0/board-2.bin` | 2,253,964 | `4b0cb241…` | **当前在用 BDF**（上游 board-2 + 强制条目名方案） |
| `ath12k/WCN7850/hw2.0/board-2.bin.community` | 113,356 | `d0e2bd6f…` | 社区 BDF（只有一条 88860 板级数据） |
| `ath12k/WCN7850/hw2.0/m3.bin` | 299,660 | `88c1590d…` | M3 固件（当前） |
| `ath12k/WCN7850/hw2.0/m3.bin.community` | 299,660 | `93bb73f7…` | 社区版 |
| `qca/hmtbtfw20.tlv` | 274,128 | `bcaca7b2…` | 蓝牙 BTFW（HMT = WCN7850） |
| `qca/hmtnv20.bin` | 9,592 | `c0470137…` | 蓝牙 NVM/board data |

> BDF 与板级数据必须配套：当前组合是“上游 amss + 上游 board-2 + `board_name` 强制条目”
> （见 `etc/modprobe.d/ath12k-override.conf`）。换 amss 时记得同步换 board-2/m3。

### 音频
| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `aw882xx_acf.bin` | 3,504 | `7ba6173f…` | 4×AW882xx 功放 ACF 参数（与平板 Android vendor 逐字节相同） |
| `awinic/aw88461_tb710fu.bin` | 3,504 | `7ba6173f…` | 同上（副本） |
| `Lenovo-TB710FU-tplg.bin`（firmware 根） | 17,260 | `97f9ae34…` | **当前 ALSA 拓扑 v9**（TDM 4ch 方案） |
| `qcom/sm8650/Lenovo-TB710FU-tplg.bin` | 17,260 | `97f9ae34…` | 同上（内核实际查找路径） |
| `tplg/Lenovo-TB710FU-tplg.bin` | 17,260 | `ef028921…` | 旧版拓扑（保留备用） |
| `qcom/sm8650/xiaoxin/gt/adsp.mbn` | 34,793,816 | `a0686c2b…` | **ADSP 固件**（音频 DSP；即项目里的 adsp_prc.mbn） |
| `qcom/sm8650/xiaoxin/gt/adsp_dtb.mbn` | 65,336 | `4b2480da…` | ADSP DTB |
| `qcom/sm8650/xiaoxin/gt/{adspr,adsps,adspua,battmgr,cdspr}.jsn` | ~0.5 KB×5 | 见清单 | remoteproc jsn |

### 视频 / GPU（SM8650）
| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `qcom/sm8650/xiaoxin/gt/cdsp.mbn` | 5,951,912 | `3354368b…` | CDSP |
| `qcom/sm8650/xiaoxin/gt/cdsp_dtb.mbn` | 36,664 | `b55da59b…` | CDSP DTB |
| `qcom/sm8650/xiaoxin/gt/vpu33_4v.mbn` | 2,339,528 | `7cc7775c…` | **Iris VPU 固件**（视频编解码，6/6 格式实测通过） |
| `qcom/sm8650/xiaoxin/gt/gen70900_sqe.fw` | 85,364 | `5db88197…` | Adreno 750 GPU SQE |
| `qcom/sm8650/xiaoxin/gt/gen70900_aqe.fw` | 33,176 | `c09717d8…` | GPU AQE |
| `qcom/sm8650/xiaoxin/gt/gmu_gen70900.bin` | 78,588 | `be6925bd…` | GPU GMU |
| `qcom/sm8650/xiaoxin/gt/gen70900_zap.mbn` | 12,088 | `ee7681af…` | GPU zap |

### 触摸
| 文件 | 大小 | md5 | 说明 |
|---|---|---|---|
| `novatek/novatek_nt36532_fw.bin` | 245,760 | `bca72e40…` | Novatek NT36532 触摸固件（开机由 nvt_36xxx 驱动烧录） |

---

## 4. 驱动模块清单（`board-root/lib/modules/7.2.0-gcf72cbb39da8-dirty/`）

30 个 .ko，全部是**相对内核 7.2.0-gcf72cbb39da8-dirty 重编/打过补丁**的版本
（其余约 1600 个模块属于发行版标准安装，可从 `kernel/` 的源码重编或沿用发行版包）。

| 模块（相对 `kernel/` 下的路径） | 大小 | md5 前 8 | 说明 |
|---|---|---|---|
| `extra/nvt_36xxx.ko` | 728,304 | `0fd75fef` | **Novatek SPI 触摸驱动**（外置模块，非内核树内建） |
| `drivers/net/wireless/ath/ath12k/ath12k.ko` | 4,105,768 | `ced755cf` | WiFi 核心，含 TB710FU CE 轮询/PS/聚合补丁（acm53 代） |
| `drivers/net/wireless/ath/ath12k/wifi7/ath12k_wifi7.ko` | 1,425,216 | `25478fed` | WiFi7 数据面（acm53 代） |
| `net/mac80211/mac80211.ko` | 5,958,376 | `871e1ceb` | 打过 rx.c 补丁（softirq 契约实验） |
| `drivers/bus/mhi/host/mhi.ko` | 477,776 | `ecbe8b7b` | MHI（SBL 重试补丁） |
| `drivers/power/sequencing/pwrseq-qcom-wcn.ko` | 91,912 | `d5d99e83` | WCN7850 电源时序 |
| `drivers/power/supply/qcom_battmgr.ko` | 104,512 | `01433af7` | 电池管理（ADSP） |
| `drivers/soc/qcom/apr.ko` | 97,704 | `d42ef701` | APR（音频） |
| `drivers/soundwire/soundwire-bus.ko` | 592,216 | `58d5affe` | SoundWire |
| `sound/soc/codecs/aw882xx/snd-soc-aw882xx.ko` | 1,024,736 | `6146f46c` | **AW882xx 功放驱动**（TDM 4ch 版） |
| `sound/soc/snd-soc-core.ko` | 1,325,080 | `0ff1819e` | ASoC 核心（补丁） |
| `sound/soc/qcom/snd-soc-sc8280xp.ko` | 87,152 | `875cb29c` | 声卡（TDM/4ch 补丁） |
| `sound/soc/qcom/snd-soc-qcom-sdw.ko` | 47,728 | `e70676aa` | SoundWire 声卡 |
| `sound/soc/qcom/snd-soc-qcom-common.ko` | 71,040 | `0989a864` | |
| `sound/soc/qcom/snd-soc-qcom-offload-utils.ko` | 38,392 | `ecdace28` | |
| `sound/soc/qcom/qdsp6/*.ko`（15 个） | — | 见清单 | q6apm/q6afe/q6asm/q6adm/q6prm/q6core/q6usb/snd-q6apm/snd-q6dsp-common 等 |

全量 md5 见 `checksums-board-root.md5`。

> 判断“哪些是自定义模块”的方法（重装后仍可用）：`find /lib/modules/$(uname -r) -name '*.ko' -newermt 2026-09-28`。

---

## 5. 板端配置（`board-root/etc/`、`board-root/usr/`）

### modprobe.d
| 文件 | 作用 |
|---|---|
| `ath12k-override.conf` | `options ath12k tb_rx_ampdu=1 board_name="bus=pci,vendor=17cb,device=1107,…"` —— **强制 BDF 条目名的关键**，缺了 WiFi 起不来 |
| `cfg80211-regdom.conf` | `options cfg80211 ieee80211_regdom=CN` —— 否则 5 GHz 全是 PASSIVE-SCAN |
| `tb-tdmmode.conf` | 空文件（音频 TDM 实验遗留） |

### systemd 服务（12 个，全部 enable；部署服务里已包含）
| 服务 | 脚本 | 作用 |
|---|---|---|
| `tb-wifi.service` | `tb-wifi-up.sh` | WiFi 全流程：rfkill unblock → `iw reg set CN` → 等 phy0（冷启动~110s）→ wpa_supplicant → 关联 → `busybox udhcpc -B`（**-B 必须**，校园 DHCP 服务器只回 unicast）→ 等地址。**on-demand**：`systemctl start tb-wifi.service` 或 `wifi-on` |
| `tb-wifi-kick.service` | `tb-wifi-kick.sh` | 50ms 间隔 ping 网关（WCN7850 需要主机 TX 才交付 RX） |
| `tb-wifi-watchdog.service` | `tb-wifi-watchdog.sh` | WiFi 健康监控，收不到包就重启服务 |
| `tb-wifi-unblock.service` | — | 开机解 rfkill、开 NM radio |
| `tb-wifi-regdom.service` | `tb-wifi-regdom.sh` | 开机再兜一次 CN 监管域 |
| `tb-audio-init.service` | `tb-audio-init.sh` | 音频初始化：modprobe 音频栈 → 等声卡 → TDM 路由 + 4×PA 配置；声卡不枚举时自动重启（最多 2 次） |
| `tb-touch-rebind.service` | `tb-touch-rebind.sh` | 触摸补探测：面板 DSI 复位期间 SPI 探测会失败（-22），显示管线静默后重新 bind `spi0.0` |
| `tb-panel-cycle.service` | `tb-panel-cycle`（→ python 版） | SDDM 前做一次 DRM DSI off/on 循环（冷启动闩锁竞态） |
| `tb-console-quiet.service` | `tb-console-quiet.sh` | `dmesg -n 1`：cmdline `loglevel=8 + console=tbfb` 会把内核日志画到 framebuffer，与合成器抢显示管线 |
| `tb-freeze-watch.service` | `tb-freeze-watch.sh` | 卡死取证（1 Hz 计数器） |
| `tb-stress-watch.service` | `tb-stress-watch.sh` | 压力/死机取证 |
| `tb-keyd.service` | `tb-keyd.py` | 键盘事件守护 |

### 其他
- `/etc/NetworkManager/conf.d/99-tb-wifi-unmanaged.conf`：wlp1s0 交给 tb-wifi.service，避免 NM 抢
- `/etc/NetworkManager/conf.d/99-keep-usb0.conf`：保住 USB NCM 调试链路（usb0）
- `/usr/share/udhcpc/default.script`：修好的 DHCP 脚本（busybox 导出 `$mask` 不是 `$subnet`）
- `/etc/wpa_supplicant-tb.conf`：WiFi 凭据（**tb-wifi-up.sh 每次启动会按内置 SSID/PSK 重写**）
- `/usr/share/alsa/ucm2/Qualcomm/sm8650/{MTP,QRD}/`：ALSA UCM（sm8650 声卡）
- `/usr/local/bin/tb-*`（25 个）+ `wifi-on`：全部板端脚本
- `/klogd.sh`：把 dmesg 尾部持续写 `/dev/sda13`（跨 switch_root 的日志）

---

## 6. 内核与重新编译

**当前内核**：`7.2.0-gcf72cbb39da8-dirty #185`，源码基线 = 主线 commit
`cf72cbb39da84b6f02f90c07f33b102fc10b16f0`（`patches/TB710FU-base-commit.txt`），
在其上打了 47 个文件的修改（`patches/TB710FU-full-tree.diff`）**外加一批新增文件**
（diff 里没有，必须从 `sources/kernel-tree/` 拷贝）：

```
arch/arm64/boot/dts/qcom/sm8650-lenovo-tb710fu.dts    ← 板级 DTS（权威源）
drivers/gpu/drm/panel/panel-novatek-nt36532-wqhd.c
drivers/gpu/drm/panel/panel-nt36532-wqhd-dual-dsi-dsc.c
drivers/input/touchscreen/NT36XXX_SPI/                ← nvt_36xxx 触摸驱动
drivers/regulator/aw3750x.c + aw3750x_reg.h + include/linux/aw3750x.h
sound/soc/codecs/aw882xx/                             ← 树内 AW882xx 驱动
```

重建步骤（WSL 参考环境 gcc 15.2.0 aarch64-linux-gnu）：

```bash
git checkout cf72cbb39da84b6f02f90c07f33b102fc10b16f0
git apply /path/to/rebuild-kit/kernel/patches/TB710FU-full-tree.diff
cp -r /path/to/rebuild-kit/sources/kernel-tree/* .        # 新增文件
cp /path/to/rebuild-kit/kernel/kernel-config .config
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image.gz dtbs modules
```

- 触摸驱动单独编译：`sources/build-scripts/install-nvt.ps1` + `build-modules.sh`；
  aw882xx 也有 out-of-tree 版源码（`sources/out-of-tree-drivers/aw882xx/`，历史方案）。
- 打包/刷写：`kernel/recovery_b-head-fix3.bin` 是 recovery_b 分区头部（内核+initramfs），
  `kernel/avb-fix3-recovery_b.img` 是可整分区刷写的镜像。
- DTB：当前部署版反编译在 `dtbs/onboard-dtb-real-20261003.dts`（2026-10-03 晚，含散热补丁），
  活体导出在 `dtbs/current-deployed-dtb.bin`；权威源码在 `sources/kernel-tree/…/sm8650-lenovo-tb710fu.dts`。
- BDF 编辑工具：`kernel/patches/mk-board2.py`、`patch-board2-entry.py`。

---

## 7. 日常使用（板端）

```sh
# WiFi（on-demand）
wifi-on            # 解除 blacklist，需要冷启动（长按电源 15s）
wifi-on-live       # 不重启，直接起服务（ath12k 已加载时才有用）
wifi-off           # 停服务 + 写 blacklist（下次开机不加载 ath12k）
wifi-status        # 状态总览
systemctl start tb-wifi.service    # 等价物

# 触摸失联
echo spi0.0 > /sys/bus/spi/drivers/NVT-ts/bind

# 音频排障
aplay -l ; systemctl restart tb-audio-init.service

# 日志
/root/tb-wifi.log  /root/udhcpc-tb.log  /root/wpa_supplicant-tb.log  /root/tb-wifi-watchdog.log
```

---

## 8. PC 侧工具（`tools/`）

| 工具 | 用法 |
|---|---|
| `deploy-to-board.ps1` | 一键部署 / `-VerifyOnly` 校验（见第 1 节） |
| `tb-ask.ps1` | 在板上执行 shell：`-Cmd "uname -a"` 或 `-Script x.sh -OutFile log` |
| `tb-push.ps1` | 推单个文件到板（board-listen nc 原语，带 md5 校验） |
| `tb-pull.ps1` | 从板拉单个文件到主机（带 md5 校验） |
| `enum1.sh` … `enum5.sh` | 本次采集用的枚举脚本（板端现状可随时重跑） |
| `pack-board.sh` / `pack-board2.sh` | 本次采集用的板端打包脚本 |

---

## 9. 注意事项与已知问题

1. **WiFi 是 on-demand 的**：`/etc/modprobe.d/tb-wifi-baseline.conf` 一旦存在就 blacklist ath12k
   （`wifi-off` 会写它）。重装后如果没有这个文件，加上上面 11 个 enable 的服务即可开机自动起 WiFi。
2. **RX 抖动未修完**：静态 IP 下 0% 丢包，但 RTT 200–700 ms 锯齿。已排除驱动攒包（帧 26ms 内被 reap），
   怀疑在空口/AP 侧（rx bitrate 只有 65–104 Mbps 而信号 -25 dBm）。细节见项目 `PROJECT_STATE.md` 与 `踩坑记录.md`。
3. **DHCP 必须 `-B`**：校园网 DHCP 服务器只发 unicast 应答，未配置地址的客户端收不到；
   `tb-wifi-up.sh` 已内置。NetworkManager 的 DHCP 客户端在这台机器上拿不到租约，wlp1s0 保持 unmanaged。
4. **写文件后 `sync`**：ext4 upper（overlay 持久层）无日志，崩溃前几秒的写入会丢。
5. **不要 `fastboot erase userdata`**：里面是 squashfs + 持久层。
6. **telnet 单会话**（4445）：残留会话会导致 CONNECT-FAILED，稍等重试；大文件走 HTTP/nc，别走 telnet。
7. **ath12k 加载可能在中断关闭状态下把机器搞死**（历史现象）：所以 WiFi 服务做成手动/踢活式。
8. `board-2.bin` 当前版本（`4b0cb241…`）曾用于 bdwlan 追加实验，实验前的原版是 `.pre-bdwlan-test`
   （md5 相同 —— 实验已回滚）。
9. 板端 `md5-critical.txt`（`board-capture/`）是采集时刻的权威 md5 快照，可当校验基准。

---

## 10. 校验记录

- **`board-root/` 全部 110 个文件**（固件 29 + 模块 30 + 配置/脚本 51）的 md5 已逐条与平板比对：**110/110 全部一致**
  （板端 `md5sum` 输出保留在项目 `logs/rebuild-verify-all.log`；复核脚本 `tools/verify-all.sh` 可用 `tb-ask.ps1 -Script tools/verify-all.sh` 重跑）。
- 关键 18 项（固件 11 + 模块 7）另有 `tools/deploy-to-board.ps1 -VerifyOnly` 一键复核通道。
- `checksums-board-root.md5`：110 个文件的完整清单（相对本目录）。
- `checksums-kernel-sources.md5`：`kernel/` + `sources/` 共 125 个文件。
- 板端原始 tar 包在 `_board-dump/`（`rebuild-kit-board.tgz` md5 `13e7fc9a…`，41 MB）。
- 内核产物 md5：`Image.gz-fix3` = `717f913b7cd966227d95364e49cbed1a`；
  `recovery_b-head-fix3.bin` = `7fc1acb748531149e04ee4712944880c`；
  `avb-fix3-recovery_b.img` = `28c76e7160c593d7930903be9354d402`。
