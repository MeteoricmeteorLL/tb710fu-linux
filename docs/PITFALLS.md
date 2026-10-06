# Pitfalls worth knowing / 值得知道的坑

A curated selection from this port's bring-up log: the traps that cost hours and
the habits that untangled them.  It is deliberately not the whole day-by-day
record, and the device's cold-boot/power workflow is left out.

从本移植的调试日志里挑出来的"值钱的坑"：那些花掉几个小时的路障，以及把它们解开的方法。
这里**故意不是**按天记的完整流水，设备冷启动/供电流程也不在其中。

Read it before you spend an evening on something in this list.  Each entry is
*what happened → why → what to do*, and the last line of each group is the rule of
thumb.

动手前扫一眼，能省掉一个晚上。每条都是"现象 → 原因 → 对策"，每组最后一句是可复用的口诀。

---

## 1. Storage and partitioning / 存储与分区

**Every unit must be in 4 KiB sectors.**  This UFS reports 4096-byte logical
sectors, so a number worked out in 512-byte sectors is off by 8× and silently
ruins the table.  Always read `sgdisk --print /dev/sda` first, and this device's
`sgdisk` accepts **long options only** (`--new=`, not `-n`).

**所有单位都必须是 4K 扇区。** 这台 UFS 报 4096 字节逻辑扇区，用 512 字节算出来的数字
会差 8 倍、静默毁掉分区表。先 `sgdisk --print /dev/sda` 再动手；本机的 `sgdisk` **只认
长选项**（`--new=`，不是 `-n`）。

**Leave the last sectors alone.**  The backup GPT lives in the last few sectors of
the disk; a partition that runs to the very end can overwrite it.  We stop 6
sectors short.

**最后几个扇区别碰。** 备份 GPT 在盘尾；分区顶到最末尾会把它盖掉。我们停在末尾前 6 个扇区。

**Keep Android's own type GUID on `userdata`.**  With a different type Android
refuses to format the partition.  `sgdisk --backup=` first: one file restores the
whole table if a number comes out wrong.

**`userdata` 必须保留安卓自己的类型 GUID**，否则安卓拒绝格式化该分区。动手前先
`sgdisk --backup=` —— 数值不对时一个文件就能把整张表恢复回来。

**"Installed" is not "present".**  On the old, damaged persistent layer, `dpkg` said
`ii` while `ldd` reported the library missing.  Verify software by *running* it,
not by its package state.

**"装了"不等于"在盘上"。** 在早期受损的持久层上，`dpkg` 显示 `ii` 而 `ldd` 说库不存在。
验证一个软件靠**用它**，不是靠包管理器状态。

> Rule of thumb: partition numbers are the one thing here you cannot undo — read
> them from the device, never from a document.
> 口诀：分区数值是这里唯一无法反悔的东西 —— 从设备读，别从文档抄。

## 2. Boot chain and U-Boot / 引导链与 U-Boot

**U-Boot runs at EL1 here, so `armv8_switch_to_el2()` is a no-op** (it detects it
is not at EL2 and returns).  The kernel never starts.  Call the entry point
directly: `kentry(dtb, NULL, NULL, NULL)` with the arm64 protocol (`x0` = DTB,
`x1…x3` = 0).

**本板 U-Boot 跑在 EL1，`armv8_switch_to_el2()` 是空操作**（检测到不在 EL2 就直接
return），内核永远进不去。必须直接调入口：`kentry(dtb, NULL, NULL, NULL)`，按 arm64
协议 `x0`=DTB、`x1…x3`=0。

**`.bss` must be zero before the kernel starts.**  The kernel clears it only in
`early_map_kernel()`, after `primary_entry` has already read a `.data` variable
from the early idmap code — garbage there kills the kernel before it can print.
Zero the image tail yourself.

**内核启动前 `.bss` 必须是零。** 内核只在 `early_map_kernel()` 之后清它，而之前
`primary_entry` 已经读过 early idmap 代码里的一个 `.data` 变量 —— 那里有垃圾就会在能打印
之前就死。所以要自己把镜像尾部清零。

**Only `init_sequence_r[0..14]` runs.**  A full `dm_autoprobe` hangs this board, so
everything is brought up by hand.

**只跑 `init_sequence_r[0..14]`。** 完整的 `dm_autoprobe` 会挂死，其余设备都是手动拉起。

**The fixup that disables every `qcom,geni-uart` also killed Bluetooth.**  The
Bluetooth UART is a GENI UART with a `bluetooth` child node — exempt it (that is
what the `uart14fix` lineage does).

**那条"把所有 `qcom,geni-uart` 置 disabled"的 fixup 顺手把蓝牙也杀了。** 蓝牙串口就是
带 `bluetooth` 子节点的 GENI UART —— 要跳过它（`uart14fix` 谱系做的就是这件事）。

**The memboot windows are fixed and silently truncate.**  Kernel 16 MiB at 0,
initramfs 8 MiB at 16 MiB, DTB 160 KiB at 24 MiB.  A DTB larger than the window is
cut off without a word.

**memboot 的窗口是固定的，且会静默截断。** 内核 16MiB@0、initramfs 8MiB@16MiB、
DTB 160KiB@24MiB —— 超出的部分一声不响地被切掉。

**The DTS `width` must equal the real stride.**  `width = 640` on a 3200-pixel
panel produced diagonal striping instead of a picture.

**DTS 里的 `width` 必须等于真实 stride。** 3200 像素的面板上写 `width = 640`，画面不是
花屏而是**斜纹**。

**A diag build looks exactly like a dead board.**  The `diag` U-Boot images exist
to be photographed, not to boot: they print the *previous* crash's PC/FAR/ESR from
stale IMEM and then feed the watchdog forever.

**诊断构建看起来和"板子死了"一模一样。** `diag` 系列 U-Boot 是"只拍照不引导"的：它们
打印的是**上一次**崩溃的 PC/FAR/ESR（来自 IMEM 的陈旧数据），然后永久喂看门狗。

**`bootonce-bootloader` (misc BCB) must be cleared**, or the device loops back into
fastboot instead of booting.

**`bootonce-bootloader`（misc 分区里的 BCB）用完必须清**，否则会循环回 fastboot 而不是启动。

**U-Boot overwrites `/chosen` bootargs.**  Kernel module parameters therefore
cannot come from the device tree — put them in `/etc/modprobe.d/`.  (That is also
why `cfg80211 ieee80211_regdom` needs a modprobe.d file even though it is a module
parameter.)

**U-Boot 会覆盖 `/chosen` 的 bootargs**，所以内核模块参数不能走设备树 —— 写
`/etc/modprobe.d/`。（这也是为什么 `cfg80211 ieee80211_regdom` 虽然是模块参数，也得写成
modprobe.d 文件。）

## 3. Kernel build / 内核构建

**Three traps, all of which produce a kernel that is quietly wrong:**

1. **`CONFIG_ARCH_QCOM` accidentally off.**  Every symbol `depends on ARCH_QCOM`
   (~300: QCOM_APR, SND_SOC_QCOM, GENI, SERIAL_MSM…) becomes *invisible* to
   Kconfig, and `olddefconfig` deletes them — including the "not set" comment you
   were looking for.  Symptom: a module is running on the board and you cannot
   grep its CONFIG in the tree.
2. **`make olddefconfig` without `ARCH=arm64`** parses the config with the host's
   Kconfig: ARM64-only symbols disappear and the compiler description is rewritten
   to the host's gcc.
3. **`make modules` on its own always fails modpost** (thousands of `undefined!`),
   because modpost needs vmlinux's symbol table from a complete pass.  Build
   `Image.gz modules` in one command.

**三个坑，共同点是"产出一个静默错误的内核"：**

1. **`CONFIG_ARCH_QCOM` 被误关**：所有 `depends on ARCH_QCOM` 的符号（约 300 项）对
   Kconfig **彻底不可见**，`olddefconfig` 会把它们连同"未设置"注释一起删掉。症状是
   "模块在板上跑着，树里却 grep 不到它的 CONFIG"。
2. **`make olddefconfig` 忘带 `ARCH=arm64`**：按宿主的 Kconfig 解析，ARM64 专有符号整行
   消失，编译器描述也被改写成宿主 gcc。
3. **单独 `make modules` 必挂 modpost**（海量 `undefined!`），因为 modpost 需要一次完整
   构建里 vmlinux 的符号表。请一条命令构建 `Image.gz modules`。

**`/proc/config.gz` is the only authoritative running config** (when `IKCONFIG=y`);
a config file sitting in a repository is a snapshot, not the truth.

**`/proc/config.gz` 才是运行内核配置的唯一权威**（在 `IKCONFIG=y` 时）；仓库里的配置文件
只是历史快照。

**Incremental builds keep stale objects.**  Disabling a config does not remove the
target's `.o`, so the old code stays linked in — `rm` it and rebuild.  The same
trap appears the other way round: an out-of-tree driver and an in-tree driver with
the same `compatible` both register, and you get "already registered".

**增量构建不会清掉过期目标文件。** 关掉一个 config 并不会删对应 `.o`，旧代码还链在
里面 —— 手动 `rm` 再全量重编。反向的同一个坑：外挂驱动与树内驱动用同一个 `compatible`
会重复注册（`already registered`）。

**`make Image` can fail for reasons unrelated to what you are working on** while
`make modules` succeeds.  A link error in a display driver blocked `vmlinux` while
audio work continued happily against the existing `Image`.

**`make Image` 可能因为与你当前工作无关的原因失败，而 `make modules` 正常**：一个显示
驱动的链接错误挡住了 `vmlinux`，音频那边的调试照旧能用旧的 `Image` 进行。

## 4. Display / 显示

**DSC needs its PPS first.**  A 128-byte PPS (0x9E) must be sent to both DSI hosts
in LP mode *before* the encoder is configured; otherwise the picture is black no
matter how right the encoder settings are.

**DSC 必须先发 PPS。** 在配置编码器之**前**，要以 LP 模式向两个 DSI host 发送 128 字节
PPS（0x9E）；否则编码器配置再对也是黑屏。

**0x11 and 0x29 take no arguments** — sending them in the "short write + 1
parameter" form does not work.

**0x11 与 0x29 是无参数命令** —— 用"短写 + 1 个参数"的格式发过去不生效。

**The DSI link clock is fixed at 1.198 Gbps/lane.**  Change the refresh rate with
the vertical porch, not the clock.

**DSI link 时钟固定 1.198 Gbps/lane。** 改刷新率要调 vertical porch，不要动时钟。

**Novatek panels fail a warm init** — the VCI rail has to be fully cycled before
initialising, or the panel simply does not respond.

**Novatek 面板热态初始化会失败** —— 必须先让 VCI 彻底断电再初始化，否则面板完全不响应。

**Reading DSC/PLL/PHY registers at run time is fatal** (SError, unrecoverable).
Read the configuration out of kernel logs instead.

**运行时读 DSC/PLL/PHY 寄存器会致命**（SError 不可恢复）。要看配置就从内核日志里看。

**GPIO 74 must be reserved.**  Reading it locks the bus and freezes the whole
machine — hence `gpio-reserved-ranges = <32 8>, <74 1>` in the DTS.

**GPIO 74 必须保留。** 读它会把总线锁死、整机冻结 —— 所以 DTS 里要写
`gpio-reserved-ranges = <32 8>, <74 1>`。

## 5. Touch / 触摸

**Interrupts were swallowed by the PDC layer.**  Upstream's `sm8650.dtsi` gives
`tlmm` a `wakeup-parent = <&pdc>`, and the touch GPIO is in the PDC map — so
pinctrl marks it `skip_wake_irqs`, `set_type`/`unmask` return early, and the
tlmm interrupt registers are **never programmed** (they sat at their reset values
while the line pulsed).  This board's PDC does not deliver, so nothing worked.
Fix: `/delete-property/ wakeup-parent;` on `&tlmm` in the DTS — this port has no
system suspend, so the PDC's wake capability is not needed.

**中断被 PDC 层吞掉了。** 上游 `sm8650.dtsi` 给 `tlmm` 加了 `wakeup-parent = <&pdc>`，
而触摸 GPIO 在 PDC 映射表里 —— 于是 pinctrl 把它标成 `skip_wake_irqs`，
`set_type`/`unmask` 全部提前 return，**tlmm 的中断寄存器从未被编程**（线在跳，寄存器
还是复位值）。本板的 PDC 又不投递，所以怎么都不出点。修法：DTS 里
`/delete-property/ wakeup-parent;`（本移植没有系统休眠，用不到 PDC 唤醒）。

**The vendor driver hard-codes the trigger type** (`IRQ_TYPE_EDGE_RISING`); the DT
flags for that interrupt are never used for it.

**vendor 驱动把触发类型写死了**（`IRQ_TYPE_EDGE_RISING`），设备树里那个中断的 flags
从不参与触发类型。

**DSI error recovery silently kills the touch firmware.**  The screen and the
digitizer are one chip (DDIC); when the DSI host resets or re-enables its PHY, the
touch firmware dies with no log at all — `nvt_check_fw_status failed`, "FW info is
broken".  The fix is a health workgroup that polls every 5 s and reflashes the
firmware (~250 ms).

**DSI 的错误恢复会静默杀死触摸固件。** 屏和触控是同一颗 DDIC；DSI host 复位或重新使能
PHY 时，触控固件会无声无息地死掉（`nvt_check_fw_status failed`、"FW info is broken"）。
对策是一个健康检查工作组：每 5 秒轮询，失联就重刷固件（约 250ms）。

**Do not enable the vendor's ESD protection** (`NVT_TOUCH_ESD_PROTECT`): it triggers
on interrupt idle time, so an untouched screen makes it reflash forever.

**别开 vendor 的 ESD 保护**（`NVT_TOUCH_ESD_PROTECT`）：它按"中断空闲时间"触发，屏幕
没人碰时会永远循环重刷。

**`rmmod` + `insmod` left the IRQ disabled.**  `remove()` did not unregister its
platform device, so the second probe failed with `-EBUSY` and the error path left
the freshly requested IRQ disabled.  Unregister the platform device in `remove()`.

**`rmmod` + `insmod` 之后中断是关的。** `remove()` 没有注销自己注册的 platform
device，第二次 probe 在 `platform_device_register` 处 `-EBUSY` 失败，错误路径把刚申请的
中断留在了 disabled 状态。修法是在 `remove()` 里注销那个 platform device。

**Autoload needs the right modalias.**  The device is `spi:NVT-ts-spi`, which the
`of:` alias does not match — add an `spi_device_id` table so udev loads the module.

**自动加载要看 modalias。** 设备的 modalias 是 `spi:NVT-ts-spi`，`of:` 别名匹配不上 ——
加一张 `spi_device_id` 表，udev 才会自动加载。

## 6. Audio / 音频

**"Our registers match the vendor's 100 %" does not mean it works.**  A 110-register
dump matched the vendor ACF exactly and the amplifiers stayed silent, because the
vendor's configuration describes the **vendor's bus**.  The chip's receiver was set
to MSB-justified/32-bit/64 fs (matching Android's TDM) while the mainline path fed
it Philips I2S/16-bit/32 fs — the receiver never locks, `BSTS`/`SWS` stay 0, and the
amplifier's start check fails forever.  Fix: clear `I2SCTRL1[9:4]` before every
start (`I2SCTRL2 = 0`).  **The chip locking its PLL was the biggest red herring** —
it can lock the bit clock and still not match the frame structure.

**"寄存器与厂商 100% 一致"不等于能用。** 110 个寄存器与厂商 ACF 逐项吻合、功放依然静音
—— 因为厂商那套配置描述的是**厂商的总线**。芯片接收机被配成 MSB-justified/32bit/64fs
（配 Android 的 TDM），而主线路径给的是 Philips I2S/16bit/32fs —— 接收机永远不锁定
（`BSTS`/`SWS` 恒 0），功放的 start 检查永远不过。修法：每次 start 前清
`I2SCTRL1[9:4]`（`I2SCTRL2 = 0`）。**芯片能锁 PLL 恰恰是最大的误导** —— 它能锁位时钟，
却对不上帧结构。

**When a chip's registers all look right, check the bus's physical format**: mode,
bit width, BCLK ratio, WS polarity, slot mapping.  That is where the answer is.

**当一颗芯片的寄存器全都"对"的时候，去核对总线的物理格式**：模式、位宽、BCLK 比、
WS 极性、槽位映射 —— 答案在那里。

**Online register poking beats rebuilding.**  The AW882xx driver exposes a sysfs
`reg` (full read/write), `rw` (single read) and per-amp switches, so orthogonal
experiments — and the I2SCTRL scan that found the fix — needed no kernel rebuild.

**在线改寄存器胜过重编内核。** AW882xx 驱动暴露了 sysfs `reg`（整体读写）、`rw`（单寄存器
读）和逐颗开关，所以正交实验（包括最后找到解的那次 I2SCTRL 扫描）不用重编内核。

**ALSA topology names must match the kernel's.**  The vendor tplg uses downstream
widget names (`SEC RX0 TDM0 Playback`) that mainline's LPASS port names do not
match (`Secondary TDM0 Playback`) → "Failed to add route", `-19`, card never
instantiates.  Rewrite the names in place (the fields have slack).

**ALSA 拓扑里的名字必须和内核一致。** vendor 的 tplg 用下游命名
（`SEC RX0 TDM0 Playback`），主线 LPASS 端口叫 `Secondary TDM0 Playback`，匹配不上 →
`Failed to add route`、`-19`、卡起不来。把名字就地改写（那些字段有富余）。

**A tplg written for another ABI reads as zeros.**  The PCM caps were in an old
layout, so the kernel read zeros for rates/channels and **every** `aplay` failed
with `-22` while the kernel logged nothing.  Confirm the layout with an `offsetof`
probe before writing caps.

**为另一套 ABI 写的 tplg 会读出一片零。** PCM caps 是旧布局，内核读到的采样率/声道数
全零，于是**每次** `aplay` 都 `-22`，而内核**一行日志都没有**。写 caps 之前先用
`offsetof` 探针确认布局。

**The ADSP firmware contains a product subset of modules.**  A topology that
references a module id this firmware does not have fails `GRAPH_OPEN` with status 1
and no detail.  Isolate it: trim the graph to one module, then probe
`PARAM_ID_*` SET_CFG (0 = accepted, 3 = unsupported) to learn what the firmware
actually knows.

**ADSP 固件里只有产品的模块子集。** 拓扑引用了固件没有的模块 id 时，`GRAPH_OPEN` 只回
status 1、没有任何细节。定位办法：把图缩到只剩一个模块，再用 `PARAM_ID_*` 的 SET_CFG
探针（0=收下、3=不认识）反推固件认识什么。

**QRTR announcements race the ADSP.**  `qrtr_smd` loaded by udev *after* the ADSP
started announcing, so the announcements were lost and PDR never saw `audio_pd` →
`q6apm` never probed.  Put `qrtr_smd` in `modules-load.d` so it is up first.

**QRTR 的宣告与 ADSP 抢跑。** `qrtr_smd` 由 udev 在 ADSP 开始宣告**之后**才加载，宣告丢了，
PDR 永远等不到 `audio_pd`，`q6apm` 就不探测。把 `qrtr_smd` 放进 `modules-load.d`。

**Port coordinates are validated by the firmware.**  `sd_line_idx` must be 1 for the
secondary TDM port (0 is rejected), and the classic I2S module only accepts classic
formats — `S16_LE`/2ch starts, forced `S32_LE`/4ch does not.  Mainline has no
representation for a 4-slot TDM interface.

**端口坐标是固件在校验的。** 次级 TDM 端口的 `sd_line_idx` 必须是 1（0 会被拒），经典
I2S 模块只接受经典格式 —— `S16_LE`/2ch 能起，强推 `S32_LE`/4ch 不行。主线对 4 槽 TDM
接口还没有表达手段。

**Verify playback at the driver, not at the tool.**  `aplay` returning 0 means
nothing; check `/proc/asound/card0/pcm0p/sub0/status` for `state: RUNNING` and an
advancing `delay`, and grep dmesg for xrun/underrun.

**在驱动层验证播放，别信工具。** `aplay` 返回 0 什么也不能说明；要
`/proc/asound/card0/pcm0p/sub0/status` 里 `state: RUNNING` 且 `delay` 在走，并且 dmesg
里 xrun/underrun 计数为 0。

## 7. WiFi / WLAN

**"Connected but useless" was four separate bugs**, not one:

1. a stale rfkill soft-block plus NetworkManager's radio being off — `nmcli radio
   all` and `rfkill list` first, every time; `iw scan` succeeding does not mean the
   higher layer may use the device;
2. regulatory domain `00` — every 5 GHz channel is passive-scan only; set `CN`
   both as a module parameter and at boot;
3. the DHCP client must ask for **broadcast replies**: the server answers unicast
   to an address the client does not have yet, so the OFFER is dropped.  busybox
   `udhcpc -B` fixes it, NetworkManager's client cannot;
4. the DHCP script used `$subnet` while busybox exports `$mask`, so the address was
   added as `…/` and silently failed — **"lease obtained" with no address on the
   interface**.  When a lease arrives and nothing appears, check the script's
   variable names first.

**"连上了但没法用"是四个独立的问题，不是一个：** ① 残留的 rfkill 软阻塞 + NM 的 radio
关（每次都先看 `nmcli radio all` 和 `rfkill list`；`iw scan` 能扫不代表能用）；② 监管域
`00`（5GHz 全被动扫描），模块参数与开机各设一次 `CN`；③ DHCP 必须请求**广播应答**（服务
器对客户端还没有的地址回 unicast，OFFER 被丢），busybox `udhcpc -B` 解决，NM 的客户端
做不到；④ DHCP 脚本用了 `$subnet` 而 busybox 导出的是 `$mask`，地址被加成 `…/` 静默失败
—— **"租约拿到了但网卡上什么都没有"**。租约到了却看不到地址，先看脚本变量名。

**This chip does not hand frames up unless the host transmits.**  Measured,
monotonic: with no host traffic the RTT to the gateway was ~190 ms; a 20/s ping
brought it to ~92 ms; 100/s to 44 ms — and packet loss rises with the rate.  So
"kicking" is a knob with two ends, and **MMIO/config reads from the host do not
count** — it has to be a real frame on the air.

**这颗芯片"没人跟它说话就不交包"。** 实测单调：不发东西时到网关 RTT ≈190ms，20/s 降到
≈92ms，100/s 降到 44ms —— 而丢包随速率上升。所以"踢"是一个两头都痛的旋钮，而且**主机侧
读 MMIO/config 不算数**，必须是真空口发一帧。

**The old BA workaround was stale.**  dmesg showed one `unable to perform ampdu
action 0 … ret -95` per second (the AP asking for a block-ack session, the driver
refusing).  Accepting them made RX work properly — 0 % loss and 2–3× throughput.
`options ath12k tb_rx_ampdu=1` (read at hw registration, so reload the module).

**那个"别开 BA 会话"的老 workaround 已经过期。** dmesg 里每秒一条
`unable to perform ampdu action 0 … ret -95`（AP 请求块确认、驱动全拒）。接受之后 RX 反而
正常 —— 0% 丢包、吞吐 2~3 倍。`options ath12k tb_rx_ampdu=1`（hw 注册时读取，改完要重载）。

**Monitor mode only shows your own TX.**  This chip's RX never appears on a `mon0`
capture, so judge QoS from the frame-control bytes of the TX you *can* see.

**监听模式只能看到自己的发送。** 这颗芯片的接收从不出现在 `mon0` 抓包里，所以判断 QoS 要
看你能抓到的**发送帧**的帧控制字节。

**Some things are decided by the firmware and are not host-fixable.**  Our frames
go out as non-QoS; forcing the host side to advertise QoS broke the 4-way
handshake.  The firmware re-headers in both paths.  Record the mechanism and move
on.

**有些事由固件决定，主机侧改不动。** 我们的数据帧在空口上是非 QoS；从主机侧强行改成
QoS 会让四次握手超时。固件在两条路径上都要自己重组头部。把机制记下来，别耗在这。

**The watchdog must watch the right thing.**  Death shows up as the RX counter
freezing (`tb_poll_rx`) with `wmi command … timeout` / `failed to transmit frame`,
**not** as a failed ping — a busy campus network drops pings too, so a ping-based
watchdog kills healthy machines.  A second, quieter death is losing the lease
(L2 connected, address present, **no default route**) with RX still flowing: catch
that with a route check and re-run `udhcpc -B` in place.

**看门狗要盯对东西。** 死亡的表现是 RX 计数冻结（`tb_poll_rx`）加
`wmi command … timeout` / `failed to transmit frame`，**不是** ping 不通 —— 繁忙的校园网
自己就丢 ping，用 ping 判死会误杀正常的机器。还有第二种更安静的死法：租约丢了（L2 连着、
地址也在、但**没有默认路由**）而 RX 还在涨 —— 用路由检查发现它，就地重跑 `udhcpc -B`。

**Aggressive polling values can wedge the machine.**  Making the poll fast and the
budget large (2 ms/1024) killed the board with the journal stopping at the last
poll line and no panic.  The default 20 ms/64 was already the fastest throughput.

**激进的轮询参数会把机器搞死。** 把周期调到 2ms、预算调到 1024，板子直接死，journal 停在
最后一条轮询日志上、没有 panic。默认的 20ms/64 已经是最快的吞吐配置。

**A bad BDF does not fail cleanly and does not recover.**  A wrong board data file
gives `qmi failed to load bdf file … -110` and then `failed to send QMI message …
-5`; restoring the file and reloading the driver does **not** bring it back — only
a chip reset does.  Back up first, and expect one reboot per BDF experiment.

**坏的 BDF 既不干净失败、也回不来。** 用错板级数据文件会先 `-110` 再
`failed to send QMI message … -5`；把文件换回来、重载驱动**都救不回来** —— 只有复位芯片
才行。动手前备份，并做好"每次实验要重启一次"的心理准备。

**Look at the first four bytes before trusting an extension.**  A file named
`bdwlan.e01` was a 32-bit ARM **ELF** — Qualcomm ships the BDF inside an ELF shell,
and the container wants the whole ELF as its payload, not the `.data` section.

**信扩展名之前先看前四个字节。** 一个叫 `bdwlan.e01` 的文件其实是 32 位 ARM **ELF** ——
高通的 BDF 装在 ELF 外壳里，而容器要的负载是**整个 ELF**，不是 `.data` 段。

**A `.orig` backup is not automatically a rollback point.**  Restoring
`ath12k_wifi7.ko.orig` made WiFi fail to probe (`Unknown hardware version … 0xf`)
because that module had been patched too.  A trustworthy rollback point is a
source rebuild whose md5 matches what is running.

**`.orig` 备份不一定是回退点。** 还原 `ath12k_wifi7.ko.orig` 之后 WiFi 直接探测失败
（`Unknown hardware version … 0xf`），因为那个模块也被改过。可信的回退点是"从源码重建 +
md5 与实际运行的一致"。

**Throughput numbers need a control on the same path.**  The mirror caps a single
connection at ~1 MB/s — a PC downloading through the same network measured the
same, so the "WiFi is 1 MB/s" conclusion was wrong.  Also: this network blocks
client-to-client TCP (handshake fine, RST on the first data packet), so measure
with one-way UDP counters, not with a board-to-PC transfer.

**吞吐数字要在同一条路径上做对照。** 镜像站把单连接限在 ~1MB/s —— 用 PC 走同一条网络下载
也是这个数，所以"WiFi 只有 1MB/s"的结论是错的。另外这个网络拦截客户端互访的 TCP（握手
正常、第一个数据包就 RST），所以要用单向 UDP 计数法，别用板子↔PC 互传。

**Heavy RX wedges the NIC.**  Four concurrent streams (~2–3 MB/s) killed the chip
mid-download.  Step up gradually, and know that this can require a reset.

**重载接收会把网卡压死。** 四路并发（约 2~3MB/s）会让芯片在下载中途死掉。要压测就小步
加，并且知道这可能需要重启一次。

## 8. Measurement and tooling habits / 度量与工具习惯

**Turn guesses into numbers.**  Counters (ticks, rx, max_gap, slow) proved the
driver was not batching frames, which moved the search to the air side; a second
station on the same SSID (3 ms to the gateway, 223 ms to the tablet) cleared the
network in five minutes.  Both beat another hour of reading code.

**把猜测变成数字。** 计数器（ticks/rx/max_gap/slow）证明了驱动没有攒包，把调查推向空口
侧；同一个 SSID 上的第二台 STA（到网关 3ms、到平板 223ms）五分钟就排除了网络。两者都比
再看一小时代码有用。

**Use kernel timestamps, and write to tmpfs.**  `tcpdump -tt`, or `-w` then `-r`.
Writing each packet to a slow (and then damaged) filesystem fabricated "batches of
eight" — the same loop against `/dev/shm` showed the real timing.

**用内核时间戳，写到 tmpfs。** `tcpdump -tt`，或 `-w` 后再 `-r`。把每个包写进慢速（当时
还损坏的）文件系统会伪造出"每 8 个一批"的假象 —— 同样一段代码写 `/dev/shm` 才是真节奏。

**`pkill -f <script>` kills the script itself** (its own command line matches).
Put the kill outside the script.

**`pkill -f <脚本名>` 会把脚本自己杀掉**（匹配到自己的命令行）。把 kill 放到脚本外面。

**Python buffers output**: use `-u`, or write once at the end, or the file sits at
0 bytes while the script runs.

**Python 输出是带缓冲的**：用 `-u`，或者只在结束时写一次，否则脚本还在跑时文件一直是
0 字节。

**On the board, long commands need `setsid … &` plus a marker file** — a dropped
console sends SIGHUP and the command dies mid-flight.

**板上的长命令要 `setsid … &` + 标记文件** —— 控制台一断，SIGHUP 就把命令杀掉。

**Snapshot `dmesg` at boot.**  A chatty driver logs hundreds of KB per minute; after
six minutes the ring buffer only holds the last few minutes, and the early boot
evidence is gone.

**开机就把 `dmesg` 存下来。** 话多的驱动每分钟几百 KB，六分钟后环形缓冲只剩最近几分钟，
早期启动证据就没了。

**Git Bash rewrites `/tmp/x`-style arguments into Windows paths.**  Set
`MSYS2_ARG_CONV_EXCL='*'` (or use `//tmp/x`) when passing such paths to a remote
shell.

**Git Bash 会把 `/tmp/x` 这类参数改写成 Windows 路径。** 往远端 shell 传这类路径时设
`MSYS2_ARG_CONV_EXCL='*'`（或用 `//tmp/x`）。

**PowerShell may read a BOM-less UTF-8 script as GBK**, so a non-ASCII regex in it
silently never matches.  Keep script-side matching ASCII, or add a BOM.

**PowerShell 可能把无 BOM 的 UTF-8 脚本按 GBK 读**，脚本里的非 ASCII 正则于是永远不匹配。
脚本里做匹配就用 ASCII，或者给文件加 BOM。

**PowerShell swallows a WSL command's exit status.**  Confirm a build succeeded by
grepping its log for `error:`, not by trusting `$?`.

**PowerShell 会吞掉 WSL 命令的退出码。** 判断构建是否成功要靠日志里 grep `error:`，别信
`$?`。

**Windows has no inbox RNDIS driver** — use the CDC-NCM gadget for the debug link
(that is what this port does), and give the gadget a fixed serial number so the
host keeps the same adapter identity.

**Windows 没有自带 RNDIS 驱动** —— 调试链路用 CDC-NCM（本移植就是），并给 gadget 一个
固定序列号，让主机侧网卡身份稳定。

## 9. Power / 供电

**A 100 mA USB port cannot carry an unattended boot.**  The inrush of boot +
panel + WiFi can brown out on a weak supply and leave the board stuck part-way,
with no log at all.  For unattended runs, use a supply that negotiates more
current.

**100mA 的 USB 口撑不住无人值守的启动。** 启动 + 面板 + WiFi 上电的瞬态电流会在弱供电下
把电压拉垮，板子卡在半路、连日志都没有。要跑长时间无人值守，换成能协商更大电流的供电。

**Diagnose that state from the PC:** a device showing as
`USB\VID_0000&PID_0002` in `Get-PnpDevice -PresentOnly -Status Error` means the USB
controller is alive but enumeration or boot did not finish — as opposed to a truly
powered-off board (no device at all) or a live one (a normal descriptor).

**从 PC 侧判别这种状态**：`Get-PnpDevice -PresentOnly -Status Error` 里出现
`USB\VID_0000&PID_0002`（描述符请求失败）= USB 控制器活着但枚举/启动没走完；完全断电是
连设备都没有，活着则有正常的描述符。

> Rule of thumb: when a "hang" is being blamed on a subsystem, check the supply and
> the journal first — one of our "WiFi crashes" was a clean reboot, and one
> "death" was a brown-out.
> 口诀：怀疑"卡死"时先看供电和 journal —— 我们遇到的"WiFi 崩溃"有一次是干净重启，
> 有一次是掉电。
