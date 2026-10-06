# Status by subsystem / 各部位支持情况

What works on this port today, what is half-way, and what has not been touched.
Everything marked ✅ or ⚠️ was observed on the real device; ❓ means nobody has
tried it; ❌ means it is known not to work.

本移植目前各部位的状态。标 ✅/⚠️ 的都是在实机上观察到的，❓ 表示还没人试过，
❌ 表示已知不可用。

Legend / 图例: ✅ works · ⚠️ partial / 部分可用 · ❌ not working / 不可用 ·
❓ untested / 未验证 · ➖ no such hardware / 本机无此硬件

| Part / 部位 | | Notes / 说明 |
|---|---|---|
| Boot chain / 启动链 | ✅ | ABL → `boot_b` (U-Boot) → `linboot` slot (kernel + initramfs + DTB) → `linsys` rootfs → systemd → SDDM → Plasma. Cold boot to desktop ~40–60 s. / 冷启动到桌面约 40–60 秒 |
| Kernel / 内核 | ✅ | mainline **7.2.0** (`7.2.0-gcf72cbb39da8-dirty`), 49 files changed plus new drivers; `kernel/Image.gz` is byte-identical to the running kernel. / 主线 7.2.0，49 个文件改动；`kernel/Image.gz` 与实机运行的内核逐字节相同 |
| Panel / 面板 | ✅ | Novatek NT36532 dual-DSI 3200×2000, DSC. **Latch race**: sometimes lit but blank on a cold boot — `tb-panel-cycle.service` does a real DRM off/on before SDDM and fixes it. / 冷启动偶发"有背光无画面"，已用 DRM off/on 服务绕过 |
| Backlight / 背光 | ✅ | `sy7758` over I²C, brightness slider works. / 亮度可调 |
| Touch / 触摸 | ✅ | Novatek NT36532 over SPI (`nvt_36xxx`, out of tree). The DSI reset makes the SPI probe fail on some cold boots — `tb-touch-rebind.service` re-binds it. / 冷启动偶发探测失败，已有重新 bind 服务 |
| GPU / 图形 | ✅ | Adreno 750 (gen70900), `msm` built in. The IFPC quirk for this chip id is removed (see §4.1 of KNOWN-ISSUES) — without that the machine froze. `glxgears` measured **120 FPS** under XWayland. / 去掉 IFPC quirk 后才稳定；glxgears 实测 120 FPS |
| Video codec / 视频编解码 | ✅ | Iris VPU firmware loads (`vpu33_4v.mbn`); 6/6 formats passed during bring-up. / VPU 固件可用，点亮阶段 6/6 格式通过 |
| **Speaker output / 扬声器输出** | ⚠️ | The path is **wired up end to end**: codec, four AW882xx amps and topology probe, the card enumerates and sound comes out. It is **badly distorted** — crackling/clipping at any volume — which points at the ACF parameter set (still written for the vendor's MSB/32-bit/64 fs bus) or per-amplifier gain. Nobody has measured it yet; that is the next step (KNOWN-ISSUES §3, PITFALLS §6). / 链路**已打通**（codec/功放/拓扑都探测成功、声卡枚举、能出声），但**声音很炸**（任意音量都爆音/削波），指向 ACF 参数（仍按厂商 MSB/32bit/64fs 总线写的）或逐颗功放增益；还没人实测过，这是下一步 |
| Microphone / 麦克风 | ❓ | Untested. / 未验证 |
| Headphones (wired) / 有线耳机 | ❓ | Untested; the amplifier path is shared with the speakers. / 未验证；与扬声器共用功放通路 |
| **Bluetooth audio / 蓝牙音频** | ✅ | **Tested with headphones** (the only sink tried) — sound comes through. No other Bluetooth sink, and no profile beyond A2DP playback, has been exercised. / **用耳机测过**（目前唯一试过的输出设备），能出声；其它蓝牙输出与 A2DP 之外的模式未验证 |
| **WiFi** | ⚠️ **+ crash hazard** | WCN7850 / `ath12k` associates and gets a lease (`phy0` only appears ~110 s after a cold boot), but latency sawtooths 200–700 ms, rx bitrate stays at 65–104 Mbps at −25 dBm, and RX needs a host TX keepalive (`tb-wifi-kick`). **It has also hung/reset this board and still prints `NOHZ tick-stop error` softirq warnings**, which is why it is loaded on demand rather than at boot. Details and what to capture before you poke it: KNOWN-ISSUES §2. / 能连能拿地址但延迟抖动、速率低、需要保活；**而且它把本机搞死过、现在仍会打软中断告警**，所以是按需加载 |
| Bluetooth | ⚠️ | Transport up: `hci_uart` on `uart14` (the `uart14fix` U-Boot lineage), firmware loads. Pairing/audio untested. / 传输层可用（uart14 需保留），配对与音频未验证 |
| USB device (NCM) | ✅ | The gadget carries the rescue console: board `192.168.7.2`, host `192.168.7.1`, `ssh`, `nc 4444`, `telnet 4445`. This is the lifeline when there is no display. / 救援控制台走这条链路，没有显示时它是唯一入口 |
| USB host / OTG | ⚠️ | An OTG keyboard was used during bring-up. Host mode from the running desktop is not verified. / 点亮阶段用过 OTG 键盘，桌面下的 host 模式未验证 |
| Storage / 存储 | ✅ | UFS 256 GB, 4096-byte logical sectors, ext4 root. Two harmless `vdd-hba`/`vccq2` regulator warnings. The boot framebuffer reservation is fixed, so large files are no longer corrupted (KNOWN-ISSUES §1). / 大文件静默损坏已修 |
| Battery reporting / 电量显示 | ⚠️ | `upower` shows it (needs its system user and `PrivateUsers=no` under a root session). `qcom_battmgr` intermittently logs `-110` on some properties. / 图标可用，个别属性偶发 -110 |
| Charging / 充电 | ⚠️ | Charges over USB-C (the device ran on it throughout bring-up); charge-current/health reporting not verified. / 能充电，电流/健康度上报未验证 |
| Thermal / 温度 | ❓ | The deployed DTB carries a thermal patch; zones exist. Not validated under sustained load. / DTB 含散热补丁，未做持续负载验证 |
| Suspend / resume | ❓ | Never tried. Expect this to need work (the panel latch and GMU power states are the usual suspects). / 从未试过 |
| Sensors (accelerometer / gyro / ALS) | ❌ | Not enabled in the device tree — no rotation, no auto-brightness. / 设备树里没启用 |
| Camera | ❌ | No bring-up at all. / 完全未做 |
| Cellular modem / GNSS | ➖ | This unit is WiFi-only; no modem or GNSS bring-up. / 本机无蜂窝/GNSS |
| Stylus / 手写笔 | ❓ | Not tried. / 未试 |
| Virtual keyboard / 虚拟键盘 | ✅ | maliit, wired into kwin's `InputMethod`. / maliit，已接进 kwin |
| X11 apps / X11 程序 | ✅ | Works through XWayland, which needs `/tmp/.X11-unix` to exist. Images packed on or before 2026-10-06 have `/` owned by uid 197609, which makes `systemd-tmpfiles` skip every entry and leaves that directory missing — every X11 app then fails with `couldn't open display`. One-line fix in KNOWN-ISSUES §6; `glxgears` measures 120 FPS. / 通过 XWayland 可用，但它需要 `/tmp/.X11-unix`；2026-10-06 及更早的镜像 `/` 属主错误会让 tmpfiles 全线失效（修法见 KNOWN-ISSUES §6），glxgears 实测 120 FPS |
| Chromium / VLC | ✅ | Both installed and working (Chromium via a wrapper that adds `--no-sandbox --password-store=basic --ozone-platform=wayland`). / 都能用，Chromium 走包装脚本 |
| `snap` / `flatpak` | ❌ | `CLONE_NEWUSER` returns `EPERM` even for root on this port, so both are impossible. Use debs. / 用户命名空间不可用，只能用 deb |
| Desktop / 桌面 | ✅ | Plasma 6 Wayland, SDDM with root auto-login, Chinese UI available, virtual console on `tty1`, battery/backlight/keyboard applets working. / Plasma 6 Wayland + root 自动登录 |
| Chinese UI / input / 中文界面与输入 | ✅ | Chinese locale and KDE translations install with the image; fcitx5 data present. / 中文界面可用 |
| Clock / DNS / 时间与解析 | ✅ | Needed two fixes (`dns=none` + `tb-timesync.service`), otherwise the clock sat at 1970 and DNS broke. / 已修 |
| Rescue console / 救援控制台 | ✅ | In the initramfs, on USB NCM, independent of the rootfs; also brings a shell when `linsys` is empty or broken. / 在 initramfs 里，不依赖 rootfs |
| Installing another distro / 换其他发行版 | ✅ | The initramfs only needs GPT partition `linsys`, ext4, and `/etc/os-release`; see `docs/INSTALL.md` §4 and `docs/ROOTFS.md`. / 只看分区名 + ext4 + `os-release` |
| Recovery image / 第三方 recovery | ➖ | None is shipped or hosted here; bring your own. / 本仓库不提供，自行准备 |

## The short version / 一句话总结

A usable Linux tablet: it boots, the screen and touch work, the GPU is stable,
USB and storage are solid, and you can install anything whose packages do not
need user namespaces.  It is **not** yet a daily driver for media: **the speakers
play, but the sound is badly distorted**, WiFi is slow, and
suspend/sensors/camera have not been touched —
and there is one memory-corruption bug that used to bite large file writes, which
this repository fixes (see `docs/KNOWN-ISSUES.md` §1).

一台能用的 Linux 平板：能启动、屏幕与触摸可用、GPU 稳定、USB 与存储可靠，可以装任何
不依赖用户命名空间的软件。但**还不能当影音日常机**：**扬声器能出声但声音很炸**、WiFi 慢，
suspend/传感器/相机完全没做 —— 另外那个会让大文件写入静默损坏的内存 bug，本仓库已经
修掉了（见 `docs/KNOWN-ISSUES.md` 第 1 节）。
