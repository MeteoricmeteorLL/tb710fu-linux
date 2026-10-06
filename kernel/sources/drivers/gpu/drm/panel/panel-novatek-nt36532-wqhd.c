// SPDX-License-Identifier: GPL-2.0-only
/*
 * Novatek NT36532 WQHD Dual-DSI Panel Driver
 *
 * TB710FU v41: faithful port of the working reference driver
 * (panel-nt36532-wqhd-dual-dsi-dsc.c, shared via the TB710FU mainline
 * group).  Adaptations for this tree, each noted inline:
 *   - avdd comes from the AW37504 ENP/ENN enable pins (avdd-en-gpios,
 *     TLMM 90/91) instead of an awinic,aw37504 regulator node, which our
 *     DTB does not carry;
 *   - backlight is optional (the SY7758 rail is driven by its own
 *     driver here, so no backlight phandle in the panel node);
 *   - MIPI_DSI_MODE_DSC_ALL_SLICES_IN_PKT is kept so our unpatched host
 *     uses 2 slices per packet (the reference relies on a patched
 *     dsc_slice_per_pkt field for the same effect).
 *
 * Based on panel-novatek-nt36532e.c architecture,
 * integrating values from panel-nt36532-wqhd-dual-dsi-dsc.c
 */

#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/gpio.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_graph.h>
#include <linux/regulator/consumer.h>
#include <drm/drm_of.h>
#include <video/mipi_display.h>

#include <drm/display/drm_dsc.h>
#include <drm/display/drm_dsc_helper.h>
#include <drm/drm_connector.h>
#include <drm/drm_crtc.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>

#define DSI_NUM_MIN 1

struct panel_info {
	struct drm_panel panel;
	struct drm_connector *connector;
	struct mipi_dsi_device *dsi[2];
	struct panel_desc *desc;
	enum drm_panel_orientation orientation;

	struct gpio_desc *reset_gpio;
	struct regulator_bulk_data supplies[3];
};

struct panel_desc {
	unsigned int width_mm;
	unsigned int height_mm;

	unsigned int bpc;
	unsigned int lanes;
	unsigned long mode_flags;
	enum mipi_dsi_pixel_format format;

	const struct drm_display_mode *modes;
	unsigned int num_modes;
	const struct mipi_dsi_device_info dsi_info;
	int (*init_sequence)(struct panel_info *pinfo);

	bool is_dual_dsi;

	struct drm_dsc_config dsc;
};

static inline struct panel_info *to_panel_info(struct drm_panel *panel)
{
	return container_of(panel, struct panel_info, panel);
}

static int __maybe_unused nt36532_wqhd_init_sequence(struct panel_info *pinfo)
{
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = pinfo->dsi[0] };

	/* Commands sent only to dsi0 here; our dual-DSI manager mirrors the
	 * video stream, and the reference relies on that too (it used
	 * qcom,sync-dual-dsi on its patched host).  TB710FU bring-up kept the
	 * explicit dual writes to be safe on the unpatched host. */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0x2a);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xbc, 0x66, 0x06);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0xf0);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfa, 0x05);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x76, 0x16);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0x27);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xd0, 0x13);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xd1, 0x54);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xd2, 0x38);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xde, 0x40);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xdf, 0x02);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0x23);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x00, 0x80);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x05, 0x24);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x07, 0x00);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x08, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x09, 0xc2);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x10, 0x00);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x11, 0x03);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x12, 0xeb);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x15, 0x15);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x16, 0x13);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x30, 0xff);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x31, 0xff);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x32, 0xff);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x33, 0xfc);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x34, 0xf9);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x35, 0xf5);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x36, 0xf2);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x37, 0xf0);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x38, 0xed);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x39, 0xeb);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x3a, 0xe8);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x3b, 0xe5);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x3d, 0xe3);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x3f, 0xe0);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x40, 0xde);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x41, 0xdb);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x58, 0xff);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x59, 0xff);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x5a, 0xfa);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x5b, 0xf7);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x5c, 0xf2);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x5d, 0xeb);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x5e, 0xe3);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x5f, 0xd9);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x60, 0xd1);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x61, 0xcc);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x62, 0xc7);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x63, 0xbf);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x64, 0xba);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x65, 0xb5);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x66, 0xb0);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x67, 0xab);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x19, 0x00);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x1a, 0x02);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x1b, 0x04);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x1c, 0x08);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x1d, 0x0e);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x1e, 0x14);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x1f, 0x18);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x20, 0x1e);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x21, 0x22);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x22, 0x26);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x23, 0x2a);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x24, 0x30);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x25, 0x34);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x26, 0x38);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x27, 0x3c);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x28, 0x3f);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x29, 0x10);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x2b, 0x28);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0x25);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xc0, 0x0c);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0x24);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x98, 0x80);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xff, 0x10);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xfb, 0x01);
	/* Enable pwm */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x51, 0x0f, 0xff);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x53, 0x24);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x55, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x3b, 0x03, 0xea, 0x1a, 0x04, 0x04, 0x00);

	/* DSC Enable + PPS in the reference slot (v47 restores DSC video;
	 * v45/v46's no-DSC TPG round is over - the missing piece was
	 * qcom,sync-dual-dsi atomic command mirroring, not DSC). */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x90, 0x03);

	{
		struct drm_dsc_picture_parameter_set pps_buf;
		int i;

		drm_dsc_pps_payload_pack(&pps_buf, &pinfo->desc->dsc);
		for (i = 0; i < 2; i++) {
			int ret = mipi_dsi_picture_parameter_set(pinfo->dsi[i], &pps_buf);

			if (ret < 0)
				pr_err("TBPANEL47 pps dsi%d failed: %d\n", i, ret);
		}
	}

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x9d, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xb2, 0x91);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0xb3, 0x40);

	/* Start Display */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x11);
	msleep(120);

	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, pinfo->dsi[0], pinfo->dsi[1], 0x29);
	msleep(20);

	return dsi_ctx.accum_err;
}

static const struct drm_display_mode nt36532_wqhd_modes[] = {
	{
		/* 120Hz (v47: back from the 30Hz TPG diagnostic) */
		.clock = (3200 + 276 + 16 + 32) * (2000 + 26 + 2 + 232) * 120 / 1000,
		.hdisplay = 3200,
		.hsync_start = 3200 + 276,
		.hsync_end = 3200 + 276 + 16,
		.htotal = 3200 + 276 + 16 + 32,
		.vdisplay = 2000,
		.vsync_start = 2000 + 26,
		.vsync_end = 2000 + 26 + 2,
		.vtotal = 2000 + 26 + 2 + 232,
	},
};

static struct panel_desc nt36532_wqhd_desc = {
	.modes = nt36532_wqhd_modes,
	.num_modes = ARRAY_SIZE(nt36532_wqhd_modes),
	.dsi_info = {
		.type = "NT63532-lenovo",
		.channel = 0,
		.node = NULL,
	},
	.width_mm = 185,
	.height_mm = 150,
	/* TB710FU v72: back to 10bpc/RGB101010/DSC 1.2.  The ABL snapshot
	 * proves it: ABL's REG_DSI_VIDEO_MODE_CTRL reads 0x02009140 (the 0x140
	 * low nibble = 10bpc) where ours read 0x2009130 (0x130 = 8bpc), so the
	 * vendor node's qcom,mdss-dsi-bpp = <30> is what ABL actually drives.
	 * v62 had reverted this to the QQ-group driver's 8bpc; ABL wins. */
	.bpc = 10,
	.lanes = 4,
	.format = MIPI_DSI_FMT_RGB101010,
	/* NB: the vendor's bllp-power-mode / bllp-eof-power-mode have no
	 * MIPI_DSI_MODE_* counterpart in this tree, so they are left out. */
	.mode_flags = MIPI_DSI_MODE_VIDEO | MIPI_DSI_CLOCK_NON_CONTINUOUS |
		      MIPI_DSI_MODE_LPM | MIPI_DSI_MODE_DSC_ALL_SLICES_IN_PKT,
	.init_sequence = nt36532_wqhd_init_sequence,
	.is_dual_dsi = true,
	.dsc = {
		.dsc_version_major = 0x1,
		.dsc_version_minor = 0x2,
		.slice_height = 20,
		.slice_width = 800,
		.slice_count = 2,
		.bits_per_component = 10,
		.bits_per_pixel = 8 << 4,
		.block_pred_enable = true,
	},
};

static void nt36532_reset(struct panel_info *pinfo)
{
	gpiod_set_value_cansleep(pinfo->reset_gpio, 1);
	usleep_range(10000, 11000);
	gpiod_set_value_cansleep(pinfo->reset_gpio, 0);
	usleep_range(10000, 11000);
	gpiod_set_value_cansleep(pinfo->reset_gpio, 1);
	usleep_range(10000, 11000);
	gpiod_set_value_cansleep(pinfo->reset_gpio, 0);
	usleep_range(10000, 11000);
}

/* TB710FU v43: aliveness probes.  A live panel fresh out of reset answers
 * GET_DISPLAY_ID with 3 bytes and GET_POWER_MODE with a byte; zero bytes
 * back means the LP path never reaches the die.  The vendor TE output on
 * TLMM 86 toggles ~24x/100ms once the panel is initialized and refreshing. */
static void __maybe_unused nt36532_probe_reads(struct panel_info *pinfo, const char *tag)
{
	u8 rx[3];
	ssize_t rid, rpm;
	int i;

	/* TB710FU v60: ask *both* links.  If the panel only ever answers on
	 * dsi1 then everything we have sent to dsi0 has been going to its
	 * unconnected/slave port, which alone would explain 46 rounds of
	 * silence while ABL (which drives the pair the other way round)
	 * lights the screen. */
	for (i = 0; i < 2; i++) {
		if (!pinfo->dsi[i])
			continue;

		rx[0] = rx[1] = rx[2] = 0xff;
		rid = mipi_dsi_dcs_read(pinfo->dsi[i], MIPI_DCS_GET_DISPLAY_ID, rx, 3);
		pr_err("TBPANEL42 %s dsi%d display_id ret=%zd rx=%02x %02x %02x\n",
		       tag, i, rid, rx[0], rx[1], rx[2]);

		rx[0] = 0xff;
		rpm = mipi_dsi_dcs_read(pinfo->dsi[i], MIPI_DCS_GET_POWER_MODE, rx, 1);
		pr_err("TBPANEL42 %s dsi%d power_mode ret=%zd val=%#x\n",
		       tag, i, rpm, rx[0]);
	}
}

/* TB710FU v57: decode the panel reset pad (GPIO133) completely.
 * TLMM layout: +0x00 GPIO_CFG (pull[1:0], func_sel[4:2], drv[7:6], oe[9]),
 *              +0x04 GPIO_IN_OUT (in[0], out[1]).
 *  - oe=0        -> the pad is NOT driven at all (line floats/pulled low)
 *  - oe=1, out=0 -> gpiolib drove 0, i.e. the ACTIVE_LOW flag was not
 *                   applied and the panel has been held in reset all along
 *  - oe=1, out=1, in=0 -> driven high but the line is loaded low (hardware)
 */
static void nt36532_pad_reads(void)
{
	void __iomem *tlmm = ioremap(0xf100000, 0x300000);
	u32 cfg133, io133;

	if (!tlmm) {
		pr_err("TBPADS tlmm ioremap failed\n");
		return;
	}

	cfg133 = readl_relaxed(tlmm + 133 * 0x1000);
	io133 = readl_relaxed(tlmm + 133 * 0x1000 + 4);
	pr_err("TBPADS2 rst133 cfg=%#x io=%#x (pull=%u func=%u oe=%u drv=%u in=%u out=%u)\n",
	       cfg133, io133,
	       cfg133 & 3, (cfg133 >> 2) & 7, (cfg133 >> 9) & 1, (cfg133 >> 6) & 3,
	       io133 & 1, (io133 >> 1) & 1);

	pr_err("TBPADS panel_rst133=%d te86=%d int162=%d rst161=%d enp90=%d enn91=%d\n",
	       io133 & 1,
	       readl_relaxed(tlmm + 86 * 0x1000 + 4) & 1,
	       readl_relaxed(tlmm + 162 * 0x1000 + 4) & 1,
	       readl_relaxed(tlmm + 161 * 0x1000 + 4) & 1,
	       readl_relaxed(tlmm + 90 * 0x1000 + 4) & 1,
	       readl_relaxed(tlmm + 91 * 0x1000 + 4) & 1);
	iounmap(tlmm);
}

/* TB710FU v58: cfg=0x0 on GPIO133 says the pad was never driven - but the
 * driver believes it holds the reset line.  Print the gpio number the
 * driver actually got, its direction and value, plus the pad's own
 * config after an explicit set, to find which of the two is lying. */
static void nt36532_reset_diag(struct panel_info *pinfo)
{
	void __iomem *tlmm;
	u32 cfg133, io133;

	if (!pinfo->reset_gpio) {
		pr_err("TBPADS3 reset_gpio is NULL\n");
		return;
	}
	pr_err("TBPADS3 rst num=%d dir=%d val=%d\n",
	       desc_to_gpio(pinfo->reset_gpio),
	       gpiod_get_direction(pinfo->reset_gpio),
	       gpiod_get_value_cansleep(pinfo->reset_gpio));

	/* drive it again explicitly, then look at the pad */
	gpiod_set_value_cansleep(pinfo->reset_gpio, 0);
	usleep_range(5000, 6000);
	tlmm = ioremap(0xf100000, 0x300000);
	if (tlmm) {
		cfg133 = readl_relaxed(tlmm + 133 * 0x1000);
		io133 = readl_relaxed(tlmm + 133 * 0x1000 + 4);
		pr_err("TBPADS3 after set(0): rst133 cfg=%#x io=%#x (func=%u oe=%u in=%u out=%u)\n",
		       cfg133, io133, (cfg133 >> 2) & 7, (cfg133 >> 9) & 1,
		       io133 & 1, (io133 >> 1) & 1);
		iounmap(tlmm);
	}
}

static void nt36532_te_check(struct work_struct *work);
static DECLARE_DELAYED_WORK(nt36532_te_work, nt36532_te_check);

static void nt36532_te_check(struct work_struct *work)
{
	void __iomem *base;
	int edges = -1;
	int i;

	base = ioremap(0xf100000, 0x300000);
	if (!base) {
		pr_err("TBPANEL42 te: tlmm ioremap failed\n");
		return;
	}
	/* GPIO86 IN bit - raw TLMM read, bypassing gpiolib. */
	edges = 0;
	{
		int prev = readl_relaxed(base + 86 * 0x1000 + 4) & 1;

		for (i = 0; i < 1000; i++) {
			int cur = readl_relaxed(base + 86 * 0x1000 + 4) & 1;

			if (cur != prev)
				edges++;
			prev = cur;
			udelay(100);
		}
	}
	iounmap(base);
	pr_err("TBPANEL42 te edges=%d over 100ms (0 = silent, ~24 = alive at 120Hz)\n",
	       edges);

	/* TB710FU v54: raw pad levels in the same (proven-working) mapping -
	 * GPIO162 = touch INT (die pull-up makes it HIGH when powered),
	 * GPIO161 = touch reset, GPIO90/91 = AW37504 bias enables. */
	{
		void __iomem *tlmm = ioremap(0xf100000, 0x300000);

		if (tlmm) {
			pr_err("TBPAD int162=%d rst161=%d enp90=%d enn91=%d\n",
			       readl_relaxed(tlmm + 162 * 0x1000 + 4) & 1,
			       readl_relaxed(tlmm + 161 * 0x1000 + 4) & 1,
			       readl_relaxed(tlmm + 90 * 0x1000 + 4) & 1,
			       readl_relaxed(tlmm + 91 * 0x1000 + 4) & 1);
			iounmap(tlmm);
		} else {
			pr_err("TBPAD tlmm ioremap failed\n");
		}
	}
}

static int nt36532_prepare(struct drm_panel *panel)
{
	struct panel_info *pinfo = to_panel_info(panel);
	int ret;

	/* TB710FU v74: the board dies within ~0.9s of this function being
	 * entered at vddio 1.90V - before the initramfs has written its first
	 * snapshot, which is why no crash log has ever been captured.  Hold the
	 * panel path here long enough for the initramfs snapshot loop to be
	 * running (it starts at ~1s, now every 2s), then let it die with the
	 * log on flash. */
	pr_err("TBLOG v74 holding panel init 45s so the flash log covers it\n");
	msleep(45000);
	pr_err("TBLOG v74 resuming panel init\n");

	/* TB710FU v73: marker for the flash log.  The panel node is only
	 * enabled in the fatal configuration, so this line identifies the boot
	 * that matters (and its absence identifies a reader/survivor boot).
	 * The pstoredump partition is zeroed before each run, so nothing in
	 * the snapshot is stale. */
	pr_err("TBLOG BEGIN v74 fatal config: panel prepare entered\n");

	/*
	 * TB710FU v69: kernel logs now survive on flash (the initramfs snapshots
	 * dmesg into the pstoredump partition every 10s), so the 180s hold of
	 * v68 is gone - the watchdog leaves ~60s of post-crash time for the
	 * lockup detectors to print their traces, which is what gets captured.
	 */

	/*
	 * TB710FU v44: ABL lights this panel on every boot by running the
	 * FULL cold power-up sequence - the stock supply entry carries
	 * qcom,supply-pre-off-sleep = 30ms, i.e. the vendor cuts vddio (and
	 * the rest) before re-enabling.  We boot with the panel in ABL's
	 * post-teardown warm state (sleep), and every re-init without a VCI
	 * power cycle has been ignored by the die.  Replicate the cold boot:
	 * force all controllable rails off, wait, then power up fresh.
	 */
	regulator_force_disable(pinfo->supplies[1].consumer); /* vci */
	regulator_force_disable(pinfo->supplies[2].consumer); /* vdd  */
	regulator_force_disable(pinfo->supplies[0].consumer); /* vddio */
	msleep(80);

	/*
	 * TB710FU v63: the 1.90V vddio is now set by the DTB, the way the
	 * community DTS does it (vreg_l12b_1p9: min 1.89V/max 1.91V).  v61/v62
	 * raised it from here with regulator_set_voltage() and the board
	 * stopped booting - two boots out of two - so do not touch the rail
	 * from the driver.  The TBPWR print below still reports what the rail
	 * actually settled at.
	 */

	ret = regulator_bulk_enable(ARRAY_SIZE(pinfo->supplies), pinfo->supplies);
	if (ret < 0) {
		dev_err(panel->dev, "failed to enable regulators: %d\n", ret);
		return ret;
	}
	msleep(20);

	/* TB710FU v61: what did the rail actually settle at? */
	pr_err("TBPWR vddio=%d uV vci=%d uV vdd=%d uV\n",
	       regulator_get_voltage(pinfo->supplies[0].consumer),
	       regulator_get_voltage(pinfo->supplies[1].consumer),
	       regulator_get_voltage(pinfo->supplies[2].consumer));

	/* NB: the AW37504 bias (ENP/ENN, TLMM 90/91) is held on by gpio-hogs
	 * in the board DTB - nothing to do here. */

	nt36532_reset(pinfo);

	/* TB710FU v55: is the die alive right after reset, before anything
	 * else has been sent?  Pad levels (touch INT pull-up etc.) tell us
	 * whether the Novatek die is powered at all. */
	nt36532_pad_reads();
	nt36532_reset_diag(pinfo);
	/*
	 * TB710FU v66: the DCS reads are dropped for now.  With vddio at the
	 * vendored 1.90V the panel finally answers, and from that point the
	 * board hard-locks during kernel init - no console, no userspace, no
	 * pstore record, so the bootloader's watchdog is what resets it.  A
	 * read is the only transaction where the panel drives the bus
	 * (turnaround), and these reads are pure diagnostics, so take them out
	 * and see whether the init sequence on its own gets through.
	 */

	/*
	 * TB710FU v68: init sequence restored (v67's "send nothing" was only
	 * for the 1.9V isolation test).  The DCS reads stay out - v66 showed
	 * they are not the trigger.
	 */
	ret = pinfo->desc->init_sequence(pinfo);
	if (ret < 0) {
		regulator_bulk_disable(ARRAY_SIZE(pinfo->supplies), pinfo->supplies);
		dev_err(panel->dev, "failed to initialize panel: %d\n", ret);
		return ret;
	}
	pr_err("TBPANEL68 init sequence returned %d\n", ret);

	/* TB710FU v43: TE edges 300ms later - display-on + refreshing check. */
	schedule_delayed_work(&nt36532_te_work, msecs_to_jiffies(300));

	return 0;
}

static int nt36532_disable(struct drm_panel *panel)
{
	struct panel_info *pinfo = to_panel_info(panel);
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = pinfo->dsi[0] };

	mipi_dsi_dcs_set_display_off_multi(&dsi_ctx);
	msleep(50);

	mipi_dsi_dcs_enter_sleep_mode_multi(&dsi_ctx);
	msleep(120);

	return dsi_ctx.accum_err;
}

static int nt36532_unprepare(struct drm_panel *panel)
{
	struct panel_info *pinfo = to_panel_info(panel);

	gpiod_set_value_cansleep(pinfo->reset_gpio, 1);
	regulator_bulk_disable(ARRAY_SIZE(pinfo->supplies), pinfo->supplies);

	return 0;
}

static void nt36532_remove(struct mipi_dsi_device *dsi)
{
	struct panel_info *pinfo = mipi_dsi_get_drvdata(dsi);

	drm_panel_remove(&pinfo->panel);
}

static int nt36532_get_modes(struct drm_panel *panel,
			     struct drm_connector *connector)
{
	struct panel_info *pinfo = to_panel_info(panel);
	int i;

	for (i = 0; i < pinfo->desc->num_modes; i++) {
		const struct drm_display_mode *m = &pinfo->desc->modes[i];
		struct drm_display_mode *mode;

		mode = drm_mode_duplicate(connector->dev, m);
		if (!mode) {
			dev_err(panel->dev, "failed to add mode %ux%u@%u\n",
				m->hdisplay, m->vdisplay, drm_mode_vrefresh(m));
			return -ENOMEM;
		}

		mode->type = DRM_MODE_TYPE_DRIVER;
		if (i == 0)
			mode->type |= DRM_MODE_TYPE_PREFERRED;

		drm_mode_set_name(mode);
		drm_mode_probed_add(connector, mode);
	}

	connector->display_info.width_mm = pinfo->desc->width_mm;
	connector->display_info.height_mm = pinfo->desc->height_mm;
	connector->display_info.bpc = pinfo->desc->bpc;
	pinfo->connector = connector;

	return pinfo->desc->num_modes;
}

static enum drm_panel_orientation nt36532_get_orientation(struct drm_panel *panel)
{
	struct panel_info *pinfo = to_panel_info(panel);

	return pinfo->orientation;
}

static const struct drm_panel_funcs nt36532_panel_funcs = {
	.disable = nt36532_disable,
	.prepare = nt36532_prepare,
	.unprepare = nt36532_unprepare,
	.get_modes = nt36532_get_modes,
	.get_orientation = nt36532_get_orientation,
};

static int nt36532_probe(struct mipi_dsi_device *dsi)
{
	struct device *dev = &dsi->dev;
	struct device_node *dsi1;
	struct mipi_dsi_host *dsi1_host;
	struct panel_info *pinfo;
	const struct mipi_dsi_device_info *info;
	int i, ret;

	pinfo = devm_drm_panel_alloc(dev, struct panel_info, panel,
				     &nt36532_panel_funcs, DRM_MODE_CONNECTOR_DSI);
	if (IS_ERR(pinfo))
		return PTR_ERR(pinfo);

	pinfo->supplies[0].supply = "vddio";
	pinfo->supplies[1].supply = "vci";
	pinfo->supplies[2].supply = "vdd";
	ret = devm_regulator_bulk_get(dev, ARRAY_SIZE(pinfo->supplies),
				      pinfo->supplies);
	if (ret < 0)
		return dev_err_probe(dev, ret, "failed to get regulators\n");

	pinfo->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(pinfo->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(pinfo->reset_gpio), "failed to get reset gpio\n");

	/*
	 * TB710FU v42: the AW37504 ENP/ENN pins (TLMM 90/91) are held high
	 * by gpio-hogs in the board DTB, so the LCD bias is always on and
	 * the enable pins cannot (and must not) be re-requested here - the
	 * hog claims them and devm_gpiod_get_array_optional fails with
	 * -EBUSY, which silently killed the v41 probe.
	 */

	pinfo->desc = (struct panel_desc *)of_device_get_match_data(dev);
	if (!pinfo->desc)
		return -ENODEV;

	/* If the panel is dual dsi, register DSI1 */
	if (pinfo->desc->is_dual_dsi) {
		info = &pinfo->desc->dsi_info;

		dsi1 = of_graph_get_remote_node(dsi->dev.of_node, 1, -1);
		if (!dsi1) {
			dev_err(dev, "cannot get secondary DSI node.\n");
			return -ENODEV;
		}

		dsi1_host = of_find_mipi_dsi_host_by_node(dsi1);
		of_node_put(dsi1);
		if (!dsi1_host)
			return dev_err_probe(dev, -EPROBE_DEFER, "cannot get secondary DSI host\n");

		pinfo->dsi[1] = devm_mipi_dsi_device_register_full(dev, dsi1_host, info);
		if (IS_ERR(pinfo->dsi[1])) {
			dev_err(dev, "cannot get secondary DSI device\n");
			return PTR_ERR(pinfo->dsi[1]);
		}
	}

	pinfo->dsi[0] = dsi;
	mipi_dsi_set_drvdata(dsi, pinfo);

	ret = drm_of_get_panel_orientation(dev->of_node, &pinfo->orientation);
	if (ret < 0) {
		dev_err(dev, "%pOF: failed to get orientation %d\n", dev->of_node, ret);
		return ret;
	}

	pinfo->panel.prepare_prev_first = true;

	/* TB710FU adaptation: no backlight phandle in our panel node - the
	 * SY7758 rails are driven by their own driver, so backlight is
	 * optional here. */
	drm_panel_of_backlight(&pinfo->panel);

	drm_panel_add(&pinfo->panel);

	for (i = 0; i < DSI_NUM_MIN + pinfo->desc->is_dual_dsi; i++) {
		pinfo->dsi[i]->lanes = pinfo->desc->lanes;
		pinfo->dsi[i]->format = pinfo->desc->format;
		pinfo->dsi[i]->mode_flags = pinfo->desc->mode_flags;
		pinfo->dsi[i]->dsc = &pinfo->desc->dsc;

		ret = mipi_dsi_attach(pinfo->dsi[i]);
		if (ret < 0)
			return dev_err_probe(dev, ret, "cannot attach to DSI%d host.\n", i);
	}

	return 0;
}

static const struct of_device_id nt36532_of_match[] = {
	{
		.compatible = "lenovo,nt36532-wqhd",
		.data = &nt36532_wqhd_desc,
	},
	{},
};
MODULE_DEVICE_TABLE(of, nt36532_of_match);

static struct mipi_dsi_driver nt36532_driver = {
	.probe = nt36532_probe,
	.remove = nt36532_remove,
	.driver = {
		.name = "panel-novatek-nt36532-wqhd",
		.of_match_table = nt36532_of_match,
	},
};
module_mipi_dsi_driver(nt36532_driver);

MODULE_AUTHOR("Driver Author");
MODULE_DESCRIPTION("DRM driver for Novatek NT36532 WQHD based MIPI DSI panels");
MODULE_LICENSE("GPL");
