# Known issues / 已知问题

Everything below was observed on real hardware (Lenovo Xiaoxin Pad Pro GT,
TB710FU, SM8650Q).  Nothing here is theoretical — each item says how it was
diagnosed and what to do about it.  For a one-line-per-part summary instead, see
`docs/STATUS.md`.

下面每一条都是在实机（联想小新 Pad Pro GT / TB710FU / SM8650Q）上实测到的现象，
附诊断依据和处理办法。想要"每个部位一行"的总览，见 `docs/STATUS.md`。

---

## 1. Silent memory corruption from the boot framebuffer (root-caused) / 开机动画 framebuffer 造成的静默内存损坏（已定位根因）

**Severity: high. This is the most important bug in this port.**
**严重程度：高。这是本次移植中最重要的问题。**

### Symptom / 现象

A large file comes back with different contents than were written to it:
hashing it right after writing differs from hashing it after dropping the page
cache, while the bytes on *disk* are correct.  In practice a 1–2 GiB file
usually passes, 4 GiB usually fails, and the failure is intermittent —
`gzip`, `zstd`, `tar` and every other large-file tool report corruption.

大文件写完之后内容会和写进去的不一样：刚写完立刻算哈希，和 drop 掉页缓存之后
再算哈希结果不同，而**磁盘上的数据其实是对的**。实测 1–2GiB 常常通过、4GiB 常常
失败，且时有时无 —— `gzip`、`zstd`、`tar` 等各种大文件工具都会报损坏。

### Root cause / 根因

`0xD5100000`, 25 MiB, is the bootloader's splash framebuffer.  This kernel draws
into it at that fixed physical address with `__va()`: the boot ladder colour
blocks (`tb_mark()`), the panel console (`tbfb`), a liveness gauge that draws a
green square every 10 s (`tb_gauge_draw()`), the initcall progress bar
(`tb_initcall_bar()`), and the black box's band along the bottom.  The black
box's log rings live at `0xB0000000` and `0xD6A00000`, 1 MiB each
(`tb_bb_pa[]` in `init/main.c`).

None of those regions is reserved.  U-Boot adds the reservation node
(`common/board_r.c`) but with two bugs:

```c
u32 reg[4] = { 0, 0xd5100000, 0, 0x1900000 };
fdt_add_subnode(fdt, off, "framebuffer@d5100000");
fdt_setprop(fdt, fn, "reg", reg, sizeof(reg));   /* (1) */
fdt_setprop_empty(fdt, fn, "no-map");            /* (2) */
```

1. `fdt_setprop()` copies the little-endian `u32` array straight into the
   big-endian device tree, so every cell comes out byte-reversed:
   `0xd5100000` is stored as `0x000010d5` and `0x01900000` as `0x00009001`.
   The kernel faithfully reserves 36 865 bytes at `0x10d5` — not RAM — and none
   of the real 25 MiB.  This is the nonsense address in the kernel log:
   `framebuffer at 0x1045, 0x9001 bytes`.
2. `no-map` would drop the region out of the kernel's linear map, so once (1)
   is fixed, `__va(0xd5100000)` would fault instead — which is exactly the
   shape of the long-unexplained 3.019 s boot crash.

Consequence: `/proc/iomem` reports `d5100000-d7bfffff : System RAM`, the page
allocator hands those pages out as page cache and anonymous memory, and the
drawing code keeps overwriting whatever landed there.  Because the allocator
prefers the ~5.5 GiB of high physical RAM first and only falls back to this low
region under pressure, small files never hit it and large ones do — which is
why the failure looked size-dependent and intermittent.

`0xD5100000` 起 25MiB 是 bootloader 的开机动画 framebuffer，内核在这块固定物理
地址上用 `__va()` 画东西（引导色块、面板控制台、每 10 秒一个绿方块的心跳仪、
initcall 进度条、黑匣子底部状态带），黑匣子的日志环则在 `0xB0000000` /
`0xD6A00000` 各 1MiB。这些区间**都没有被保留**：U-Boot 会加保留节点，但代码有两
个 bug —— `fdt_setprop()` 把小端的 u32 数组原样拷进大端 DTB（于是
`0xd5100000` 变成 `0x000010d5`，内核只保留了 `0x10d5` 处 36 865 字节，真正的
25MiB 一个字节都没保留，这就是日志里那句 `framebuffer at 0x1045, 0x9001
bytes`）；而且标了 `no-map`，一旦地址修正反而会让 `__va()` 翻译失败 —— 正是当年
那个无法解释的 3.019s 崩溃的形状。

结果：页分配器把这块当普通 RAM 发放，绘制代码不断改写落到这里的页缓存/匿名页。
由于分配器优先用高地址段的约 5.5GiB、只在压力下才回落到这片低地址，小文件碰不
到、大文件才中招 —— 所以故障看起来和文件大小相关、且时有时无。

### Evidence / 实测证据

Measured on the board, 3 GiB anonymous mapping, physical addresses recovered
with `/proc/self/pagemap`:

* 256 pages of the mapping landed exactly on `0xD6A00000..0xD6AFFFFF`
  (black box slot B) and held our own pattern, not kernel text;
* three pages at `0xD6400000`, `0xD63F8000`, `0xD6870000` were overwritten
  **while we were watching** with repeating pixel values `00ff00ff` /
  `000000ff`;
* those offsets are exactly where `tb_gauge_draw()` paints
  (`row 1554 × 3200 × 4 = 0xD6400000`) and where `tb_initcall_bar()` paints
  (`≈0xD6870000`);
* reading the file back **through the page cache** gave a different md5, while
  reading it back **after `echo 3 > /proc/sys/vm/drop_caches`** matched the
  data that was written — so the write path and the disk are fine and the
  corruption is RAM being overwritten at run time.

Evidence-gathering tools are in `tools/` (`pagemap-blackbox-probe2.py`,
`largefile-cache-corruption.py`, `mem-integrity.py`).

### Fix / 修法

Reserve the three regions in the device tree, **without** `no-map` (the drawing
code needs them in the linear map):

```dts
reserved-memory {
    framebuffer@d5100000   { reg = <0x00 0xd5100000 0x00 0x1900000>; };
    tb-blackbox-a@b0000000 { reg = <0x00 0xb0000000 0x00 0x100000>; };
    tb-blackbox-b@d6a00000 { reg = <0x00 0xd6a00000 0x00 0x100000>; };
};
```

Two ways to apply it, both shipped here:

* `tools/fix-dtb-fb-reserve.py <in.dtb> <out.dtb>` — surgically rewrites the
  deployed DTB (decompile with `dtc`, fix the framebuffer node's `reg`, drop
  its `no-map`, add the two black box nodes, recompile).  Use this one for the
  currently deployed image: it changes nothing else.  This is what the shipped
  `release/linboot-*.img` carries, and it is why the device in front of you is
  not corrupting files today.
* The same nodes are added to the board DTS source by
  `tools/patch-dts-fb-reserve.py`, for a kernel rebuilt from source.

**State of the U-Boot side.**  If the node is already present, U-Boot leaves it
alone — it only fills in a node that is missing (`fdt_add_subnode` fails, and
its property writes are inside that `if`) — so declaring the nodes in the DTB is
enough and the device is fixed without touching `boot_b`.  The cause is fixed in
the source as well: `tools/patch-uboot-fbreg.py` swaps the cells with
`cpu_to_fdt32()` before `fdt_setprop()` copies them, drops `no-map`, and adds the
two black box rings.  It is applied to the shipped U-Boot source tree and builds
(`u-boot.bin` 1 451 384 bytes), and `uboot/boot_b-linboot-v3-fbreg.img` is the
packed result — **not flashed here**, because the DTB already neutralises the bug
and flashing a bootloader is the one change that needs a physical power cycle if
it goes wrong.  Flash it if you want the fix to live in the bootloader itself:

```sh
dd if=uboot/boot_b-linboot-v3-fbreg.img of=/dev/block/by-name/boot_b bs=4096 conv=fsync
sync      # then power-cycle cold: hold power ~15 s, power on
```

Note that this U-Boot's libfdt has **no `fdt_setprop_cells()`** — the helper the
kernel has.  A single-cell write is `fdt_setprop_cell()`, and for a multi-cell
property you pre-swap the values (`cpu_to_fdt32()` / `cpu_to_fdt64()`) and let
`fdt_setprop()` copy them.  The only other raw-array write in this boot path is
the `/memory` node, which already did exactly that with `cpu_to_fdt64()`, so the
framebuffer node was the only place with the bug.

Cost: 27 MiB of the 7 GiB, once.

在设备树里保留这三段（**不要** `no-map`，绘制代码需要它们留在线性映射里）。
`tools/fix-dtb-fb-reserve.py` 可以直接对现网 DTB 做外科手术（其余内容一字不动），
`tools/patch-dts-fb-reserve.py` 用于从源码重建的内核 DTS。

**U-Boot 侧的状态**：节点已存在时 U-Boot 什么都不做（`fdt_add_subnode` 失败，它的属性
写入都在那个 `if` 里面），所以 DTB 里声明了就足够，不动 `boot_b` 也能修好。根因本身也在
源码里修了：`tools/patch-uboot-fbreg.py` 用 `cpu_to_fdt32()` 把值预反转后再交给
`fdt_setprop()` 拷贝、去掉 `no-map`、一并补两个黑匣子环；已打进随附的 U-Boot 源码树并
编译通过（`u-boot.bin` 1,451,384 字节），`uboot/boot_b-linboot-v3-fbreg.img` 是打包结果
—— **本机没有刷入**，因为 DTB 已经让该 bug 失效，而刷引导程序是那种万一出问题就必须物理
断电恢复的改动。若想让修复落在引导程序里，按上面那段 dd 刷入后**冷启动**。

注意这个 U-Boot 的 libfdt **没有 `fdt_setprop_cells()`**（那是内核才有的 helper）：
单 cell 用 `fdt_setprop_cell()`，多 cell 要先自己把值反转（`cpu_to_fdt32()` /
`cpu_to_fdt64()`）再交给 `fdt_setprop()` 原样拷贝。这条引导路径上另一处裸数组写入是
`/memory` 节点，它本来就用 `cpu_to_fdt64()` 做对了 —— 所以 framebuffer 节点是唯一一处
有这个 bug 的地方。代价是 7GiB 里占掉 27MiB。

### If your image does not have the fix / 如果你的镜像还没有这个修复

Check first:

```sh
dmesg | grep 'reserved mem.*framebuffer'    # expect: ... map non-reusable framebuffer@d5100000
grep -A1 'd5100000' /proc/iomem             # expect a "reserved" child inside System RAM
```

If that shows nothing, install a DTB with the three nodes (`docs/BUILD-KERNEL.md`
§4).  Until you do, treat every write larger than ~2 GiB as untrusted: verify it
rather than believing it — `zstd -t` on an artifact, and hash the file twice with
a cache drop in between (`echo 3 > /proc/sys/vm/drop_caches`).  That is exactly
what `scripts/make-release-rootfs.sh` does, and why it retries.

先按上面两条确认。若什么都没有，就换成带那三个节点的 DTB（见
`docs/BUILD-KERNEL.md` 第 4 节）。在那之前，把大于约 2GiB 的写入都当作不可信的：
`zstd -t` 校验产物，并在 drop 缓存前后各算一次哈希 —— `scripts/make-release-rootfs.sh`
就是这么做的（并且会自动重试）。

---

## 2. WiFi (ath12k / WCN7850): slow, fragile, and a crash hazard / WiFi 慢、脆弱、且有把机器搞死的风险

> ⚠️ **This driver has taken this machine down, and it still can.**  `ath12k`
> probing has hung or reset this board with no log at all, and under the current
> patches it still prints `NOHZ tick-stop error: local softirq work is pending`
> — a softirq stuck in its RX/poll path.  Treat "start WiFi" as "accept a chance
> of losing the machine", which is why this image loads it **on demand**
> (`wifi-on`, `systemctl start tb-wifi.service`) instead of at boot.  If you make
> it automatic, you are choosing that risk on every boot.  Useful state before
> you poke it: `/sys/fs/pstore` (ramoops survives a reset) and a photo of the
> panel, which carries the boot ladder and the black box lines.
>
> ⚠️ **这一路驱动把本机搞死过，而且现在仍有可能。** `ath12k` 探测曾让本板卡死或
> 重启、连日志都没留下；在当前补丁下它还会打 `NOHZ tick-stop error: local softirq
> work is pending`（软中断卡在 RX/轮询路径里）。所以请把"开 WiFi"理解成"接受一次搞
> 死机器的概率"—— 镜像里因此是**按需**加载（`wifi-on` / `systemctl start
> tb-wifi.service`）而不是开机自动；若改成自动，等于每次开机都承担这个风险。动手前
> 有用的现场：`/sys/fs/pstore`（ramoops 能跨复位保留）和面板的照片（上面有启动梯子
> 与黑匣子输出）。

**Status: association and DHCP work; latency and throughput are poor.**
**状态：能关联、能拿到 IP；延迟和吞吐都不理想。**

What works / 已经跑通的:

* PCIe link training (Gen2 x2) and enumeration of `17cb:1107`;
* the `pwrseq-qcom-wcn` power sequence, all rails enabled, RPMH clock on;
* firmware load: `amss.bin` + `board-2.bin` + `m3.bin`, MSI vectors up,
  `phy0` registers — **about 110 s after a cold boot**;
* WPA2 association and a DHCP lease.

The problems / 存在的问题:

* **Latency jitter**: static IP gives 0 % loss but RTT sawtooths between 200 ms
  and 700 ms; the rx bitrate stays at 65–104 Mbps while the signal is −25 dBm.
  Driver-side aggregation was ruled out (frames are reaped within 26 ms), so
  it looks like the air side or the AP.
  **延迟抖动**：静态 IP 下 0% 丢包，但 RTT 在 200–700ms 之间锯齿；接收速率只有
  65–104Mbps 而信号 −25dBm。已排除驱动攒包（帧 26ms 内被回收），怀疑在空口或 AP 侧。
* **The host must transmit before RX is delivered**: this board's WCN7850 needs
  host TX traffic to hand received frames up, so `tb-wifi-kick.service` pings
  the gateway every 50 ms.  Without that keepalive, RX stalls.
  **必须先有主机发送才有接收**：所以 `tb-wifi-kick.service` 每 50ms ping 一次网关。
* **DHCP must ask for broadcast replies**: the DHCP server answers unicast to
  an address the client has not configured yet, so NetworkManager's client
  never sees the OFFER.  `busybox udhcpc -B` works; the interface is therefore
  unmanaged for NM.
  **DHCP 必须用广播请求**：服务器对尚未配置的地址回 unicast，NM 的客户端收不到
  OFFER，只有 `busybox udhcpc -B` 能拿到租约（所以 wlp1s0 对 NM 是 unmanaged）。
* **Regulatory domain**: without `cfg80211 ieee80211_regdom=CN` every 5 GHz
  channel is PASSIVE-SCAN.
  **监管域**：不设 CN 时 5GHz 全是 PASSIVE-SCAN。
* **Loaded with interrupts off**: `ath12k` probing has, historically, killed
  the machine.  That is why WiFi is on-demand (`wifi-on` /
  `systemctl start tb-wifi.service`) rather than always-on in this image, and
  why the driver carries a lot of TB710FU-specific workaround code
  (CE polling, PS work, RX replenish retry — see the kernel patch).
  **中断关闭状态下加载 ath12k 曾经把机器搞死**，所以镜像里 WiFi 是 on-demand 的，
  驱动里也因此带着大量 TB710FU 专用 workaround。
* The chip's boot ROM does not start on some boots: `MHISTATUS` reads `0xff04`
  (EE = 0xF, READY never sets) and BHI ACK drifts between `-EIO` and silence.
  Retrying the MHI READY wait (patched in `drivers/bus/mhi/host/boot.c`) and a
  cold boot are the workarounds.
  **某些启动里芯片 boot ROM 不启动**（MHISTATUS 读到 0xff04，READY 不置位），
  MHI READY 重试补丁 + 冷启动是可用的绕过办法。

Use / 用法: `wifi-on`, `wifi-status`, `systemctl start tb-wifi.service`; put
your network in `/etc/tb-wifi-credentials.conf` first.
先把网络写进 `/etc/tb-wifi-credentials.conf`。

---

## 3. Audio: the path works, the speaker sound is distorted / 音频：链路已通，但扬声器声音很炸

**Status: audio plays; the speaker output is badly distorted (crackling /
clipping) at any volume.  The remaining problem is quality, not plumbing.**
**状态：能出声；但扬声器在任何音量下都严重失真（爆音/削波）。剩下的是音质问题，
不是链路问题。**

What works / 已经跑通的:

* the ADSP/CDSP firmware loads, the WCD939x codec and the four AW882xx amplifiers
  probe (`aw882xx_acf.bin` is byte-identical to the vendor's), the ALSA topology
  `Lenovo-TB710FU-tplg.bin` is loaded, and the SoundWire/LPASS plumbing
  (`snd-soc-sc8280xp`, `q6apm`/`q6afe`/`q6asm`) is built and enabled;
* the card enumerates, `aplay` plays, and **sound does come out of the
  speakers** — the routing through the LPASS macros into the AW882xx amps is
  wired up;
* **Bluetooth headphones work** — they are the only audio sink that has been
  tested over Bluetooth.

* ADSP/CDSP 固件加载、WCD939x codec 与 4 颗 AW882xx 功放探测成功（`aw882xx_acf.bin`
  与厂商逐字节相同）、ALSA 拓扑 `Lenovo-TB710FU-tplg.bin` 已加载、SoundWire/LPASS
  那一套（`snd-soc-sc8280xp`、`q6apm`/`q6afe`/`q6asm`）已编译并启用；
* 声卡能枚举、`aplay` 能放，**扬声器确实出声** —— 经 LPASS 宏到 AW882xx 功放的通路
  已经接上了；
* **蓝牙耳机可用** —— 蓝牙侧目前只测过耳机这一个输出设备。

What is wrong / 问题在哪里: the speaker output is harsh and crackling at every
volume, which is what a wrong TDM slot mapping or a wrong gain stage in the
four-channel path sounds like.  The suspects, in the order worth checking:

1. **the ACF parameter set still describes the vendor's bus.**  The amplifiers'
   receiver is configured by the ACF for MSB-justified / 32-bit / 64 fs (matching
   Android's TDM path), while the driver now forces Philips I2S / 16-bit / 32 fs
   before every start — that register write is what got sound out at all, but the
   ACF's own coefficients, gain blocks and DSP configuration were derived for the
   other format.  This is the first thing to look at;
2. **per-amplifier gain and channel mapping** — four amps fed from two channels
   (`sound-channel` / `aw-re-*` in the driver, and the properties on the four
   `aw882xx@3x` DTS nodes);
3. the codec's own speaker gain stages.

Nobody has measured the output yet: no `tinymix`/`amixer` sweep, no recording of
the analogue output.  The amplifiers expose `reg` / `rw` sysfs nodes, so gain and
I2SCTRL combinations can be swept **without rebuilding anything** — that is how
the silent-amplifier bug was found (`docs/PITFALLS.md` §6).  Do that before
theorising.

扬声器在每个音量下都刺耳、爆音 —— 这正是"四声道通路里 TDM 槽位映射错了或增益级错了"
听起来的样子。值得依次排查：

1. **ACF 参数描述的仍是厂商的总线**：功放的接收机被 ACF 配成 MSB-justified / 32bit /
   64fs（对齐 Android 的 TDM 路径），而驱动现在每次 start 前强制成 Philips I2S /
   16bit / 32fs —— 那次寄存器写入是"终于出声"的原因，但 ACF 里的系数、增益块与 DSP 配置
   是按另一套格式推出来的。这是第一个该看的地方；
2. **逐颗功放的增益与声道映射** —— 四颗功放由两个声道驱动（驱动里的 `sound-channel` /
   `aw-re-*`，以及 DTS 上四个 `aw882xx@3x` 节点的属性）；
3. codec 自身的扬声器增益级。

目前还没有人实测过输出：没做过 `tinymix`/`amixer` 扫描，也没录过模拟输出。功放驱动暴露了
`reg` / `rw` 两个 sysfs 节点，增益与 I2SCTRL 的组合可以**不重编任何东西**就扫完 —— 当
"功放静音"那个 bug 就是这么找到的（见 `docs/PITFALLS.md` 第 6 节）。先做这件事，再谈推断。

Not verified / 未验证: microphone capture, wired headphone output, and any
Bluetooth sink other than headphones (PipeWire's user units are configured for a
root session — see `docs/ROOTFS.md`).

未验证：麦克风录音、有线耳机输出，以及蓝牙侧除耳机外的输出设备（PipeWire 的用户单元
已为 root 会话配好，见 `docs/ROOTFS.md`）。

---

## 4. Instability / 系统不稳定性

Several distinct causes; two are fixed, one is item 1 above, one is open.

### 4.1 GPU / GMU fence timeouts (fixed by the kernel) / GMU 栅栏超时（已用内核修好）

`a6xx_gpu.c` logs `fenced register write` warnings and polls
`GMU_AHB_FENCE_STATUS` for 2 ms; when a transition of the GPU's inter-frame
power collapse (IFPC) state goes wrong the fence never lands and the machine
freezes silently.  Root cause: the chip entry `0x43051401` ("C520v2", Adreno
750 / gen70900) carried `ADRENO_QUIRK_IFPC` and `a750_ifpc_reglist`, which this
silicon does not honour.  The shipped kernel removes both for that chip id, so
the GMU stays in `GMU_IDLE_STATE_ACTIVE` (`Image.gz-noifpc` /
`linboot-noifpc.img`).  Symptom before the fix: hard freeze with no log;
after: clean.

### 4.2 Panel latch race (workaround installed) / 面板闩锁竞态（已装绕过）

The NT36532 dual-DSI panel sometimes comes up with the backlight on and no
picture.  A real DRM off/on cycle before the session starts fixes it, so
`tb-panel-cycle.service` runs one before SDDM (`/usr/local/bin/tb-panel-cycle`
— ctypes + libdrm).

### 4.3 The four-layer "black screen" checklist / 四层黑屏排查表

When the panel is dark, check in this order: (1) GPU firmware present under
`/lib/firmware/qcom/sm8650/xiaoxin/gt/` (`gen70900_*`, `gmu_gen70900.bin`,
`a730_*`); (2) panel latch (run `tb-panel-cycle`); (3) session actually
activated (`loginctl show-session`); (4) framebuffer blanked
(`/sys/class/graphics/fb0/blank`).

### 4.4 The kernel console fights the compositor / 内核控制台与合成器抢显示

`console=tbfb` plus `loglevel=8` draws kernel logs into the framebuffer and
fights the compositor for the display pipeline, so `tb-console-quiet.service`
runs `dmesg -n 1` at boot.  If you are debugging boot, stop that service to get
the log back on screen.

### 4.5 Still open / 仍未解决

Random restarts that are not explained by 4.1 are still open.  The kernel
carries a boot-ladder and a "black box" (see item 1 — they are also the cause
of item 1) that draw boot progress and the last lines of the previous boot onto
the panel, plus tools/ for post-mortem; `/sys/fs/pstore` (ramoops at
`0xac300000`) holds the console tail across a reset.  If you hit one, capture
`/sys/fs/pstore` and a photo of the panel before rebooting.

---

## 5. Other / 其他

* **`snap` cannot work**: `CLONE_NEWUSER` fails with `EPERM` even for root on
  this port (mount namespaces are fine), which breaks snapd, flatpak and
  anything else that needs a user namespace.  Suspected Gunyah/EL1 restriction;
  not worked around.  **Don't apt-install snapd**; use debs, or Chromium via
  the wrapper in `/usr/local/bin/chromium` (`--no-sandbox` is needed for the
  same reason).
  **`snap` 用不了**：这台机器上 `CLONE_NEWUSER` 对 root 也返回 `EPERM`（mount
  命名空间正常），snapd/flatpak 这类依赖用户命名空间的东西都不行，怀疑是
  Gunyah/EL1 的限制，尚无绕法。别装 snapd，用 deb；Chromium 走
  `/usr/local/bin/chromium` 包装脚本（同样因此需要 `--no-sandbox`）。
* **Clock**: the clock can start at 1970 because NetworkManager overwrites
  `/etc/resolv.conf` with an empty file, and DNS breaks without a correct time.
  `99-nodns.conf` (`dns=none`) plus `tb-timesync.service` handle it.
  **时间可能停在 1970**：NM 会把 `/etc/resolv.conf` 覆盖成空文件，时间不对 DNS 就
  坏。已用 `99-nodns.conf`（`dns=none`）+ `tb-timesync.service` 处理。
* **X11 apps**: everything X11 needs XWayland, which needs `/tmp/.X11-unix`;
  when that directory is missing, `glxgears` reports `couldn't open display`.
  §6 explains the ownership bug that used to keep it from being created.
  **X11 程序**：X11 程序都依赖 XWayland 与 `/tmp/.X11-unix`，目录缺失时 `glxgears`
  报 `couldn't open display`。之前让它建不出来的属主问题见 §6。
* **Root desktop apps**: the session runs as root, so user services that
  hard-code `ConditionUser=!root` (PipeWire, upower) do not start by default;
  this image overrides both.
  **root 桌面下的应用**：PipeWire、upower 等带 `ConditionUser=!root` 的用户服务
  默认不启动，镜像里已覆盖。
* **Battery reporting**: `upower` needs its system user and
  `PrivateUsers=no` (see above); without them the battery indicator is empty.
  **电池显示**：`upower` 需要系统用户并关掉 `PrivateUsers`（同因），否则电池图标为空。

---

## 6. X11 applications cannot start: `/` owned by a non-root uid / X11 程序起不来：根目录属主不是 root

### Symptom / 现象

Wayland 会话本身正常（`plasmashell`、`kwin_wayland` 都在跑），GPU 也正常，但任何
X11 程序都打不开：

```
$ glxgears
Error: couldn't open display (null)
$ DISPLAY=:0 glxinfo -B
Error: unable to open display :0
```

XWayland 根本没起来，`kwin_wayland_wrapper` 在会话启动时就报了：

```
kwin_wayland_wrapper: Failed to create Xwayland connection sockets
```

### Root cause / 根因

`/tmp/.X11-unix` 不存在。它本该由 `systemd-tmpfiles` 创建（发行版的 `x11.conf`，以及
本项目的 `/etc/tmpfiles.d/tb-x11.conf`），但 `systemd-tmpfiles --create` 直接拒绝：

```
Detected unsafe path transition / (owned by 197609) → /var (owned by root)
```

`/` 以及它下面 70 多个路径（`/usr`、`/etc`、`/etc/systemd`…）的属主是 **uid 197609**
——Windows 打包机留下的 uid——而不是 root。systemd 拒绝规范化"父目录不属于 root"的
路径，于是**所有** tmpfiles 条目都静默失效：不只是 X 的 socket 目录，还有
`/var/run/utmp`（所以 sddm 会报 `Failed to write utmpx`）等。

这是打包环节的问题，不是驱动的问题：已发布的 `tb710fu-rootfs-20261006.tar.zst` 里
`./`、`./etc/`、`./usr/` 的属主就是 `197609/197609`。已修在
`scripts/make-release-rootfs.sh`：打包前归一化属主，并且不通过就直接失败。

### Fix / 修法

已经装了旧镜像的系统，执行一次：

```
chown 0:0 /
find / -xdev \( -uid 197609 -o -gid 197609 \) -exec chown 0:0 {} +
systemd-tmpfiles --create
mkdir -p -m 1777 /tmp/.X11-unix /tmp/.ICE-unix
systemctl restart sddm
```

之后 XWayland 会自己起来，`glxinfo -B` 报 `freedreno` / `FD750` /
`direct rendering: Yes`，`glxgears` 实测 120 FPS（同步到 120Hz 面板）。

2026-10-06 之后打包的镜像由 `tb-firstboot.sh` 在首次开机时自动做这件事。

### Check / 自检

```
stat -c '%u:%g %n' /        # 必须是 0:0
ls -ld /tmp/.X11-unix       # 必须存在，1777
pgrep -a Xwayland           # 会话起来后应该有
```

### Not a GPU problem / 这不是 GPU 的问题

`glxgears` 在 Wayland 会话里本来就只能靠 XWayland 跑。要测 GPU，用
`eglinfo`（Wayland 平台会报 `FD750`）、`vkcube`（`Turnip Adreno (TM) 750`）或
`kmscube`；这台上 Adreno/freedreno 一直是好的。
