/*
 * Copyright (C) 2024 Novatek, Inc.
 *
 * $Revision: 132694 $
 * $Date: 2024-01-16 08:16:46 +0800 (週二, 16 一月 2024) $
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
 * more details.
 *
 */
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/gpio.h>
#include <linux/proc_fs.h>
#include <linux/input/mt.h>
#include <linux/of_irq.h>
#include <linux/irqdomain.h>
#include "nt36xxx.h"
#include <linux/gpio/consumer.h>
/* Kirby code for KIRBYU-960 by liaoxg1 at 2024/4/26 start */
/* Kirby code for KIRBYU-960 by liaoxg1 at 2024/4/26 end */

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
#include <drm/drm_panel.h>
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
#include <linux/msm_drm_notify.h>
#elif IS_ENABLED(NVT_FB_NOTIFY)
#include <linux/notifier.h>
#include <linux/fb.h>
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
#include <linux/earlysuspend.h>
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
#include <linux/soc/qcom/panel_event_notifier.h>
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
#include "mtk_panel_ext.h"
#include "mtk_disp_notify.h"
#endif

#include <linux/jiffies.h>
#include <linux/string.h>
#include <linux/cdev.h>
#include <linux/uaccess.h>

#define PENRAW_DRIVER_NAME "lenovo_penraw_driver"
#define PENRAW_DEVICE_NAME "lenovo_penraw"
static const unsigned int MINOR_NUMBER_START = 0; /* the minor number starts at */
static const unsigned int NUMBER_MINOR_NUMBER = 1; /* the number of minor numbers */
static unsigned int major_number; /* the major number of the device */
/* ioctl for direct access */
static struct cdev penraw_char_dev; /* character device */
static struct class* penraw_char_dev_class = NULL; /* class object */
static struct lenovo_pen_info pen_buffer[LENOVO_MAX_BUFFER];
static unsigned char pen_report_num;
static unsigned char pen_frame_no;
static unsigned char pen_buffer_wp;

#if NVT_TOUCH_ESD_PROTECT
static struct delayed_work nvt_esd_check_work;
static struct workqueue_struct *nvt_esd_check_wq;
static unsigned long irq_timer = 0;
uint8_t esd_check = false;
uint8_t esd_retry = 0;
#endif /* #if NVT_TOUCH_ESD_PROTECT */

#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
static struct delayed_work nvt_hall_check_work;
static struct workqueue_struct *nvt_hall_check_wq;
#endif
#endif

#if NVT_TOUCH_EXT_PROC
extern int32_t nvt_extra_proc_init(void);
extern void nvt_extra_proc_deinit(void);
#endif

#if NVT_TOUCH_MP
extern int32_t nvt_mp_proc_init(void);
extern void nvt_mp_proc_deinit(void);
#endif

#if NVT_CUST_PROC_CMD
#if NVT_EDGE_REJECT
extern int32_t nvt_edge_reject_set(int32_t status);
#endif
#if NVT_EDGE_GRID_ZONE
extern int32_t nvt_edge_grid_zone_set(uint8_t deg, uint8_t dir, uint16_t y1,
				      uint16_t y2);
#endif
#if NVT_PALM_MODE
extern int32_t nvt_game_mode_set(uint8_t status);
#endif
#if NVT_SUPPORT_PEN
extern int32_t nvt_support_pen_set(uint8_t status);
#endif
#ifdef BUILD_LAPIS_TOUCH
extern int32_t nvt_haptics_set(uint8_t status);
#endif
static struct work_struct ts_restore_cmd_work;
#endif
#if NVT_SET_CHARGER
extern int32_t nvt_set_charger(uint8_t charger_on_off);
bool tp_charge_flag = false;
EXPORT_SYMBOL(tp_charge_flag);
bool tp_resume_flag = false;
EXPORT_SYMBOL(tp_resume_flag);
#endif
#if WAKEUP_GESTURE
bool nvt_gesture_flag = false;
EXPORT_SYMBOL(nvt_gesture_flag);
#endif
struct nvt_ts_data *ts;
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 start */
#define DISP_ID_DET (301+125)

#if IS_ENABLED(NVT_PLATFORM_DRIVER)
static struct platform_device *nvt_ts_pdev;
#endif

#if BOOT_UPDATE_FIRMWARE
static struct workqueue_struct *nvt_fwu_wq;
extern void Boot_Update_Firmware(struct work_struct *work);
char *BOOT_UPDATE_FIRMWARE_NAME;
char *MP_UPDATE_FIRMWARE_NAME;
#endif
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 end */
/* Kirby code for KIRBYU-960 by liaoxg1 at 2024/4/26 start */
static char tp_version_info[128] = "";
/* Kirby code for KIRBYU-960 by liaoxg1 at 2024/4/26 end */
#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
static struct drm_panel *active_panel;
static int nvt_drm_panel_notifier_callback(struct notifier_block *self,
					   unsigned long event, void *data);
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
static int nvt_drm_notifier_callback(struct notifier_block *self,
				     unsigned long event, void *data);
#elif IS_ENABLED(NVT_FB_NOTIFY)
static int nvt_fb_notifier_callback(struct notifier_block *self,
				    unsigned long event, void *data);
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
static void nvt_ts_early_suspend(struct early_suspend *h);
static void nvt_ts_late_resume(struct early_suspend *h);
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
static struct drm_panel *active_panel;
static void *notifier_cookie;
static void nvt_panel_notifier_callback(enum panel_event_notifier_tag tag,
					struct panel_event_notification *event,
					void *client_data);
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
static int nvt_mtk_drm_notifier_callback(struct notifier_block *nb,
					 unsigned long event, void *data);
#endif

uint32_t ENG_RST_ADDR = 0x7FFF80;
uint32_t SPI_RD_FAST_ADDR = 0; //read from dtsi
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 start */
int gpio_125;
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 end */
#if TOUCH_KEY_NUM > 0
const uint16_t touch_key_array[TOUCH_KEY_NUM] = { KEY_BACK, KEY_HOME,
						  KEY_MENU };
#endif

#if WAKEUP_GESTURE
const uint16_t gesture_key_array[] = {
	KEY_POWER, //GESTURE_WORD_C
	KEY_POWER, //GESTURE_WORD_W
	KEY_POWER, //GESTURE_WORD_V
	KEY_POWER, //GESTURE_DOUBLE_CLICK
	KEY_POWER, //GESTURE_WORD_Z
	KEY_POWER, //GESTURE_WORD_M
	KEY_POWER, //GESTURE_WORD_O
	KEY_POWER, //GESTURE_WORD_e
	KEY_POWER, //GESTURE_WORD_S
	KEY_POWER, //GESTURE_SLIDE_UP
	KEY_POWER, //GESTURE_SLIDE_DOWN
	KEY_POWER, //GESTURE_SLIDE_LEFT
	KEY_POWER, //GESTURE_SLIDE_RIGHT
};
#endif

#ifdef CONFIG_MTK_SPI
const struct mt_chip_conf spi_ctrdata = {
	.setuptime = 25,
	.holdtime = 25,
	.high_time = 5, /* 10MHz (SPI_SPEED=100M / (high_time+low_time(10ns)))*/
	.low_time = 5,
	.cs_idletime = 2,
	.ulthgh_thrsh = 0,
	.cpol = 0,
	.cpha = 0,
	.rx_mlsb = 1,
	.tx_mlsb = 1,
	.tx_endian = 0,
	.rx_endian = 0,
	.com_mod = DMA_TRANSFER,
	.pause = 0,
	.finish_intr = 1,
	.deassert = 0,
	.ulthigh = 0,
	.tckdly = 0,
};
#endif

#if 0 /* TB710FU: MediaTek SPI platform */
const struct mtk_chip_config spi_ctrdata = {
	.rx_mlsb = 1,
	.tx_mlsb = 1,
	.cs_pol = 0,
};
#endif

static uint8_t bTouchIsAwake = 0;

/*******************************************************
Description:
	Novatek touchscreen irq enable/disable function.

return:
	n.a.
*******************************************************/
static void nvt_irq_enable(bool enable)
{
	if (enable) {
		if (!ts->irq_enabled) {
			enable_irq(ts->client->irq);
			ts->irq_enabled = true;
		}
	} else {
		if (ts->irq_enabled) {
			disable_irq(ts->client->irq);
			ts->irq_enabled = false;
		}
	}

	/* TB710FU: irq_to_desc() is not exported to modules (and the depth print
	 * was debug only), so the driver can be built as =m. */
	NVT_LOG("enable=%d\n", enable);
}

/* TB710FU: the DSI host's boot-window error handling (dsi_err_worker ->
 * dsi_sw_reset, ~15-31 s into every boot) hangs the NT36532 touch FW with
 * no log trace; from then on the die never answers SPI again and touch is
 * dead for the whole session.  The vendor ESD watchdog keys off irq idle
 * time, which would re-flash forever on an idle screen - poll the FW
 * handshake instead and re-flash only when it stops answering. */
static void nvt_fw_health_work(struct work_struct *work);
static DECLARE_DELAYED_WORK(nvt_fw_health_dwork, nvt_fw_health_work);

/* TB710FU: the generic handshake-byte probe (0xA0 pattern) never matches
 * this panel's FW - it keeps EVENT_MAP_HANDSHAKING at 0x00 even while fully
 * alive, so the poll re-flashed every ~5.9 s and touch hitched each time.
 * Probe the FW info block instead: its fw_ver/~fw_ver checksum pair is
 * maintained by FW and reads as 0xFF/0xFF garbage only when the die really
 * stopped answering SPI (the old boot-window kill). Quiet on purpose: this
 * runs every 5 s and NVT_LOG noise would churn the dmesg ring. */
static int nvt_fw_alive_probe(void)
{
	uint8_t buf[4] = { 0 };
	int i;

	usleep_range(20000, 20000);
	for (i = 0; i < 10; i++) {
		nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_FWINFO);
		buf[0] = EVENT_MAP_FWINFO;
		buf[1] = 0;
		buf[2] = 0;
		CTP_SPI_READ(ts->client, buf, 3);
		if ((uint8_t)(buf[1] + buf[2]) == 0xFF && buf[1] != 0)
			return 0;
		usleep_range(50000, 50000);
	}
	return -1;
}

static void nvt_fw_health_work(struct work_struct *work)
{
	if (nvt_fw_alive_probe()) {
		NVT_ERR("fw health: touch FW dead, re-flashing\n");
		mutex_lock(&ts->lock);
		nvt_update_firmware(BOOT_UPDATE_FIRMWARE_NAME);
		mutex_unlock(&ts->lock);
		nvt_irq_enable(true);
	}
	queue_delayed_work(system_wq, &nvt_fw_health_dwork,
			   msecs_to_jiffies(5000));
}

/*******************************************************
Description:
	Novatek touchscreen spi read/write core function.

return:
	Executive outcomes. 0---succeed.
*******************************************************/
static inline int32_t spi_read_write(struct spi_device *client, uint8_t *buf,
				     size_t len, NVT_SPI_RW rw)
{
	struct spi_message m;
	struct spi_transfer t = {
		.len = len,
	};

	memset(ts->xbuf, 0, len + DUMMY_BYTES);
	memcpy(ts->xbuf, buf, len);

	switch (rw) {
	case NVTREAD:
		t.tx_buf = ts->xbuf;
		t.rx_buf = ts->rbuf;
		t.len = (len + DUMMY_BYTES);
		break;

	case NVTWRITE:
		t.tx_buf = ts->xbuf;
		break;
	}

	spi_message_init(&m);
	spi_message_add_tail(&t, &m);
	return spi_sync(client, &m);
}

/*******************************************************
Description:
	Novatek touchscreen spi read function.

return:
	Executive outcomes. 2---succeed. -5---I/O error
*******************************************************/
int32_t CTP_SPI_READ(struct spi_device *client, uint8_t *buf, uint16_t len)
{
	int32_t ret = -1;
	int32_t retries = 0;

	mutex_lock(&ts->xbuf_lock);

	buf[0] = SPI_READ_MASK(buf[0]);

	while (retries < 5) {
		ret = spi_read_write(client, buf, len, NVTREAD);
		if (ret == 0)
			break;
		retries++;
	}

	if (unlikely(retries == 5)) {
		NVT_ERR("read error, ret=%d\n", ret);
		ret = -EIO;
	} else {
		memcpy((buf + 1), (ts->rbuf + 2), (len - 1));
	}

	mutex_unlock(&ts->xbuf_lock);

	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen spi write function.

return:
	Executive outcomes. 1---succeed. -5---I/O error
*******************************************************/
int32_t CTP_SPI_WRITE(struct spi_device *client, uint8_t *buf, uint16_t len)
{
	int32_t ret = -1;
	int32_t retries = 0;

	mutex_lock(&ts->xbuf_lock);

	buf[0] = SPI_WRITE_MASK(buf[0]);

	while (retries < 5) {
		ret = spi_read_write(client, buf, len, NVTWRITE);
		if (ret == 0)
			break;
		retries++;
	}

	if (unlikely(retries == 5)) {
		NVT_ERR("error, ret=%d\n", ret);
		ret = -EIO;
	}

	mutex_unlock(&ts->xbuf_lock);

	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen set index/page/addr address.

return:
	Executive outcomes. 0---succeed. -5---access fail.
*******************************************************/
int32_t nvt_set_page(uint32_t addr)
{
	uint8_t buf[4] = { 0 };

	buf[0] = 0xFF; //set index/page/addr command
	buf[1] = (addr >> 15) & 0xFF;
	buf[2] = (addr >> 7) & 0xFF;

	return CTP_SPI_WRITE(ts->client, buf, 3);
}

/*******************************************************
Description:
	Novatek touchscreen write data to specify address.

return:
	Executive outcomes. 0---succeed. -5---access fail.
*******************************************************/
int32_t nvt_write_addr(uint32_t addr, uint8_t data)
{
	int32_t ret = 0;
	uint8_t buf[4] = { 0 };

	//---set xdata index---
	buf[0] = 0xFF; //set index/page/addr command
	buf[1] = (addr >> 15) & 0xFF;
	buf[2] = (addr >> 7) & 0xFF;
	ret = CTP_SPI_WRITE(ts->client, buf, 3);
	if (ret) {
		NVT_ERR("set page 0x%06X failed, ret = %d\n", addr, ret);
		return ret;
	}

	//---write data to index---
	buf[0] = addr & (0x7F);
	buf[1] = data;
	ret = CTP_SPI_WRITE(ts->client, buf, 2);
	if (ret) {
		NVT_ERR("write data to 0x%06X failed, ret = %d\n", addr, ret);
		return ret;
	}

	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen read value to specific register.

return:
	Executive outcomes. 0---succeed. -5---access fail.
*******************************************************/
int32_t nvt_read_reg(nvt_ts_reg_t reg, uint8_t *val)
{
	int32_t ret = 0;
	uint32_t addr = 0;
	uint8_t mask = 0;
	uint8_t shift = 0;
	uint8_t buf[8] = { 0 };
	uint8_t temp = 0;

	addr = reg.addr;
	mask = reg.mask;
	/* get shift */
	temp = reg.mask;
	shift = 0;
	while (1) {
		if ((temp >> shift) & 0x01)
			break;
		if (shift == 8) {
			NVT_ERR("mask all bits zero!\n");
			ret = -1;
			break;
		}
		shift++;
	}
	/* read the byte of the register is in */
	nvt_set_page(addr);
	buf[0] = addr & 0xFF;
	buf[1] = 0x00;
	ret = CTP_SPI_READ(ts->client, buf, 2);
	if (ret < 0) {
		NVT_ERR("CTP_SPI_READ failed!(%d)\n", ret);
		goto nvt_read_register_exit;
	}
	/* get register's value in its field of the byte */
	*val = (buf[1] & mask) >> shift;

nvt_read_register_exit:
	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen clear status & enable fw crc function.

return:
	N/A.
*******************************************************/
void nvt_fw_crc_enable(void)
{
	uint8_t buf[8] = { 0 };

	//---set xdata index to EVENT BUF ADDR---
	nvt_set_page(ts->mmap->EVENT_BUF_ADDR);

	//---clear fw reset status---
	buf[0] = EVENT_MAP_RESET_COMPLETE & (0x7F);
	buf[1] = 0x00;
	buf[2] = 0x00;
	buf[3] = 0x00;
	buf[4] = 0x00;
	buf[5] = 0x00;
	buf[6] = 0x00;
	CTP_SPI_WRITE(ts->client, buf, 7);

	//---enable fw crc---
	buf[0] = EVENT_MAP_HOST_CMD & (0x7F);
	buf[1] = 0xAE; //enable fw crc command
	buf[2] = 0x00;
	CTP_SPI_WRITE(ts->client, buf, 3);
}

/*******************************************************
Description:
	Novatek touchscreen set boot ready function.

return:
	N/A.
*******************************************************/
void nvt_boot_ready(void)
{
	//---write BOOT_RDY status cmds---
	nvt_write_addr(ts->mmap->BOOT_RDY_ADDR, 1);

	mdelay(5);

	if (ts->hw_crc == HWCRC_NOSUPPORT) {
		//---write BOOT_RDY status cmds---
		nvt_write_addr(ts->mmap->BOOT_RDY_ADDR, 0);

		//---write POR_CD cmds---
		nvt_write_addr(ts->mmap->POR_CD_ADDR, 0xA0);
	}
}

/*******************************************************
Description:
	Novatek touchscreen enable auto copy mode function.

return:
	N/A.
*******************************************************/
void nvt_tx_auto_copy_mode(void)
{
	if (ts->auto_copy == CHECK_SPI_DMA_TX_INFO) {
		//---write TX_AUTO_COPY_EN cmds---
		nvt_write_addr(ts->mmap->TX_AUTO_COPY_EN, 0x69);
	} else if (ts->auto_copy == CHECK_TX_AUTO_COPY_EN) {
		//---write SPI_MST_AUTO_COPY cmds---
		nvt_write_addr(ts->mmap->TX_AUTO_COPY_EN, 0x56);
	}

	NVT_ERR("tx auto copy mode %d enable\n", ts->auto_copy);
}

/*******************************************************
Description:
	Novatek touchscreen check spi dma tx info function.

return:
	Executive outcomes. 0---succeed. -1---fail.
*******************************************************/
int32_t nvt_check_spi_dma_tx_info(void)
{
	uint8_t buf[8] = { 0 };
	int32_t i = 0;
	const int32_t retry = 200;

	if (ts->mmap->SPI_DMA_TX_INFO == 0) {
		NVT_ERR("error, SPI_DMA_TX_INFO = 0\n");
		return -1;
	}

	for (i = 0; i < retry; i++) {
		//---set xdata index to SPI_DMA_TX_INFO---
		nvt_set_page(ts->mmap->SPI_DMA_TX_INFO);

		//---read spi dma status---
		buf[0] = ts->mmap->SPI_DMA_TX_INFO & 0x7F;
		buf[1] = 0xFF;
		CTP_SPI_READ(ts->client, buf, 2);

		if (buf[1] == 0x00)
			break;

		usleep_range(1000, 1000);
	}

	if (i >= retry) {
		NVT_ERR("failed, i=%d, buf[1]=0x%02X\n", i, buf[1]);
		return -1;
	} else {
		return 0;
	}
}

/*******************************************************
Description:
	Novatek touchscreen check tx auto copy state function.

return:
	Executive outcomes. 0---succeed. -1---fail.
*******************************************************/
int32_t nvt_check_tx_auto_copy(void)
{
	uint8_t buf[8] = { 0 };
	int32_t i = 0;
	const int32_t retry = 200;

	if (ts->mmap->TX_AUTO_COPY_EN == 0) {
		NVT_ERR("error, TX_AUTO_COPY_EN = 0\n");
		return -1;
	}

	for (i = 0; i < retry; i++) {
		//---set xdata index to SPI_MST_AUTO_COPY---
		nvt_set_page(ts->mmap->TX_AUTO_COPY_EN);

		//---read auto copy status---
		buf[0] = ts->mmap->TX_AUTO_COPY_EN & 0x7F;
		buf[1] = 0xFF;
		CTP_SPI_READ(ts->client, buf, 2);

		if (buf[1] == 0x00)
			break;

		usleep_range(1000, 1000);
	}

	if (i >= retry) {
		NVT_ERR("failed, i=%d, buf[1]=0x%02X\n", i, buf[1]);
		return -1;
	} else {
		return 0;
	}
}

/*******************************************************
Description:
	Novatek touchscreen wait auto copy finished function.

return:
	Executive outcomes. 0---succeed. -1---fail.
*******************************************************/
int32_t nvt_wait_auto_copy(void)
{
	if (ts->auto_copy == CHECK_SPI_DMA_TX_INFO) {
		return nvt_check_spi_dma_tx_info();
	} else if (ts->auto_copy == CHECK_TX_AUTO_COPY_EN) {
		return nvt_check_tx_auto_copy();
	} else {
		NVT_ERR("failed, not support mode %d!\n", ts->auto_copy);
		return -1;
	}
}

/*******************************************************
Description:
	Novatek touchscreen eng reset cmd
    function.

return:
	n.a.
*******************************************************/
void nvt_eng_reset(void)
{
	//---eng reset cmds to ENG_RST_ADDR---
	nvt_write_addr(ENG_RST_ADDR, 0x5A);

	mdelay(1); //wait tMCU_Idle2TP_REX_Hi after TP_RST
}

/*******************************************************
Description:
	Novatek touchscreen reset MCU
    function.

return:
	n.a.
*******************************************************/
void nvt_sw_reset(void)
{
	//---software reset cmds to SWRST_SIF_ADDR---
	nvt_write_addr(ts->swrst_sif_addr, 0x55);

	msleep(10);
}

/*******************************************************
Description:
	Novatek touchscreen reset MCU then into idle mode
    function.

return:
	n.a.
*******************************************************/
void nvt_sw_reset_idle(void)
{
	//---MCU idle cmds to SWRST_SIF_ADDR---
	nvt_write_addr(ts->swrst_sif_addr, 0xAA);

	msleep(15);
}

/*******************************************************
Description:
	Novatek touchscreen reset MCU (boot) function.

return:
	n.a.
*******************************************************/
void nvt_bootloader_reset(void)
{
	//---reset cmds to SWRST_SIF_ADDR---
	nvt_write_addr(ts->swrst_sif_addr, 0x69);

	mdelay(5); //wait tBRST2FR after Bootload RST

	if (SPI_RD_FAST_ADDR) {
		/* disable SPI_RD_FAST */
		nvt_write_addr(SPI_RD_FAST_ADDR, 0x00);
	}

	NVT_LOG("end\n");
}

/*******************************************************
Description:
	Novatek touchscreen clear FW status function.

return:
	Executive outcomes. 0---succeed. -1---fail.
*******************************************************/
int32_t nvt_clear_fw_status(void)
{
	uint8_t buf[8] = { 0 };
	int32_t i = 0;
	const int32_t retry = 20;

	for (i = 0; i < retry; i++) {
		//---set xdata index to EVENT BUF ADDR---
		nvt_set_page(ts->mmap->EVENT_BUF_ADDR |
			     EVENT_MAP_HANDSHAKING_or_SUB_CMD_BYTE);

		//---clear fw status---
		buf[0] = EVENT_MAP_HANDSHAKING_or_SUB_CMD_BYTE;
		buf[1] = 0x00;
		CTP_SPI_WRITE(ts->client, buf, 2);

		//---read fw status---
		buf[0] = EVENT_MAP_HANDSHAKING_or_SUB_CMD_BYTE;
		buf[1] = 0xFF;
		CTP_SPI_READ(ts->client, buf, 2);

		if (buf[1] == 0x00)
			break;

		usleep_range(10000, 10000);
	}

	if (i >= retry) {
		NVT_ERR("failed, i=%d, buf[1]=0x%02X\n", i, buf[1]);
		return -1;
	} else {
		return 0;
	}
}

/*******************************************************
Description:
	Novatek touchscreen check FW status function.

return:
	Executive outcomes. 0---succeed. -1---failed.
*******************************************************/
int32_t nvt_check_fw_status(void)
{
	uint8_t buf[8] = { 0 };
	int32_t i = 0;
	const int32_t retry = 50;

	usleep_range(20000, 20000);

	for (i = 0; i < retry; i++) {
		//---set xdata index to EVENT BUF ADDR---
		nvt_set_page(ts->mmap->EVENT_BUF_ADDR |
			     EVENT_MAP_HANDSHAKING_or_SUB_CMD_BYTE);

		//---read fw status---
		buf[0] = EVENT_MAP_HANDSHAKING_or_SUB_CMD_BYTE;
		buf[1] = 0x00;
		CTP_SPI_READ(ts->client, buf, 2);

		if ((buf[1] & 0xF0) == 0xA0)
			break;

		usleep_range(10000, 10000);
	}

	if (i >= retry) {
		NVT_ERR("failed, i=%d, buf[1]=0x%02X\n", i, buf[1]);
		return -1;
	} else {
		return 0;
	}
}

/*******************************************************
Description:
	Novatek touchscreen check FW reset state function.

return:
	Executive outcomes. 0---succeed. -1---failed.
*******************************************************/
int32_t nvt_check_fw_reset_state(RST_COMPLETE_STATE check_reset_state)
{
	uint8_t buf[8] = { 0 };
	int32_t ret = 0;
	int32_t retry = 0;
	int32_t retry_max = (check_reset_state == RESET_STATE_INIT) ? 10 : 50;

	//---set xdata index to EVENT BUF ADDR---
	nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_RESET_COMPLETE);

	while (1) {
		//---read reset state---
		buf[0] = EVENT_MAP_RESET_COMPLETE;
		buf[1] = 0x00;
		CTP_SPI_READ(ts->client, buf, 6);

		if ((buf[1] >= check_reset_state) &&
		    (buf[1] <= RESET_STATE_MAX)) {
			ret = 0;
			break;
		}

		retry++;
		if (unlikely(retry > retry_max)) {
			NVT_ERR("error, retry=%d, buf[1]=0x%02X, 0x%02X, 0x%02X, 0x%02X, 0x%02X\n",
				retry, buf[1], buf[2], buf[3], buf[4], buf[5]);
			ret = -1;
			break;
		}

		usleep_range(10000, 10000);
	}

	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen get firmware related information
	function.

return:
	Executive outcomes. 0---success. -1---fail.
*******************************************************/
int32_t nvt_get_fw_info(void)
{
	uint8_t buf[64] = { 0 };
	uint32_t retry_count = 0;
	int32_t ret = 0;

info_retry:
	//---set xdata index to EVENT BUF ADDR---
	nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_FWINFO);

	//---read fw info---
	buf[0] = EVENT_MAP_FWINFO;
	CTP_SPI_READ(ts->client, buf, 39);
	if ((buf[1] + buf[2]) != 0xFF) {
		NVT_ERR("FW info is broken! fw_ver=0x%02X, ~fw_ver=0x%02X\n",
			buf[1], buf[2]);
		if (retry_count < 3) {
			retry_count++;
			NVT_ERR("retry_count=%d\n", retry_count);
			goto info_retry;
		} else {
			ts->fw_ver = 0;
			ts->max_button_num = TOUCH_KEY_NUM;
			NVT_ERR("Set default fw_ver=%d, max_button_num=%d!\n",
				ts->fw_ver, ts->max_button_num);
			ret = -1;
			goto out;
		}
	}
	ts->fw_ver = buf[1];
	ts->x_num = buf[3];
	ts->y_num = buf[4];
	ts->max_button_num = buf[11];
	ts->nvt_pid = (uint16_t)((buf[36] << 8) | buf[35]);
	if (ts->pen_support) {
		ts->x_gang_num = buf[37];
		ts->y_gang_num = buf[38];
	}
	NVT_LOG("fw_ver=0x%02X, fw_type=0x%02X, PID=0x%04X\n", ts->fw_ver,
		buf[14], ts->nvt_pid);

	ret = 0;
out:

	return ret;
}
/* Kirby code for KIRBYU-960 by liaoxg1 at 2024/4/26 start */
void get_tp_info(void)
{
    nvt_get_fw_info();
#ifdef BUILD_KIRBY_TOUCH
    if (gpio_125 == 0) {
        sprintf(tp_version_info, "[Vendor]:HUAXING, [TP-IC]:NT36523N, [fw]:%d\n", ts->fw_ver);
        printk("[%s]: tp_version %s\n", __func__, tp_version_info);
    } else if (gpio_125 == 1) {
        sprintf(tp_version_info, "[Vendor]:BOE, [TP-IC]:NT36523N, [fw]:%d\n", ts->fw_ver);
        printk("[%s]: tp_version %s\n", __func__, tp_version_info);
    } else {
        NVT_ERR("failed to add nt36523n tp_info\n");
    }
#else
    if (gpio_125 == 1) {
        sprintf(tp_version_info, "[Vendor]:TIANMA, [TP-IC]:NT36532, [fw]:%d\n", ts->fw_ver);
        printk("[%s]: tp_version %s\n", __func__, tp_version_info);
    } else if (gpio_125 == 0) {
        sprintf(tp_version_info, "[Vendor]:BOE, [TP-IC]:NT36532, [fw]:%d\n", ts->fw_ver);
        printk("[%s]: tp_version %s\n", __func__, tp_version_info);
    } else {
        NVT_ERR("failed to add nt36532 tp_info\n");
    }
#endif
    /* TB710FU: hqsysfs not ported */
    // hq_register_hw_info(HWID_CTP, tp_version_info);
}
/* Kirby code for KIRBYU-960 by liaoxg1 at 2024/4/26 end */
/*******************************************************
  Create Device Node (Proc Entry)
*******************************************************/
#if NVT_TOUCH_PROC
static struct proc_dir_entry *NVT_proc_entry;
#define DEVICE_NAME "NVTSPI"

/*******************************************************
Description:
	Novatek touchscreen /proc/NVTSPI read function.

return:
	Executive outcomes. 2---succeed. -5,-14---failed.
*******************************************************/
static ssize_t nvt_flash_read(struct file *file, char __user *buff,
			      size_t count, loff_t *offp)
{
	uint8_t *str = NULL;
	int32_t ret = 0;
	int32_t retries = 0;
	int8_t spi_wr = 0;
	uint8_t *buf;

	if ((count > NVT_TRANSFER_LEN + 3) || (count < 3)) {
		NVT_ERR("invalid transfer len!\n");
		return -EFAULT;
	}

	/* allocate buffer for spi transfer */
	str = (uint8_t *)kzalloc((count), GFP_KERNEL);
	if (str == NULL) {
		NVT_ERR("kzalloc for buf failed!\n");
		ret = -ENOMEM;
		goto kzalloc_failed;
	}

	buf = (uint8_t *)kzalloc((count), GFP_KERNEL | GFP_DMA);
	if (buf == NULL) {
		NVT_ERR("kzalloc for buf failed!\n");
		ret = -ENOMEM;
		kfree(str);
		str = NULL;
		goto kzalloc_failed;
	}

	if (copy_from_user(str, buff, count)) {
		NVT_ERR("copy from user error\n");
		ret = -EFAULT;
		goto out;
	}

#if NVT_TOUCH_ESD_PROTECT
	/*
	 * stop esd check work to avoid case that 0x77 report righ after here to enable esd check again
	 * finally lead to trigger esd recovery bootloader reset
	 */
	cancel_delayed_work_sync(&nvt_esd_check_work);
	nvt_esd_check_enable(false);
#endif /* #if NVT_TOUCH_ESD_PROTECT */

	spi_wr = str[0] >> 7;
	memcpy(buf, str + 2, ((str[0] & 0x7F) << 8) | str[1]);

	if (spi_wr == NVTWRITE) { //SPI write
		while (retries < 20) {
			ret = CTP_SPI_WRITE(ts->client, buf,
					    ((str[0] & 0x7F) << 8) | str[1]);
			if (!ret)
				break;
			else
				NVT_ERR("error, retries=%d, ret=%d\n", retries,
					ret);

			retries++;
		}

		if (unlikely(retries == 20)) {
			NVT_ERR("error, ret = %d\n", ret);
			ret = -EIO;
			goto out;
		}
	} else if (spi_wr == NVTREAD) { //SPI read
		while (retries < 20) {
			ret = CTP_SPI_READ(ts->client, buf,
					   ((str[0] & 0x7F) << 8) | str[1]);
			if (!ret)
				break;
			else
				NVT_ERR("error, retries=%d, ret=%d\n", retries,
					ret);

			retries++;
		}

		memcpy(str + 2, buf, ((str[0] & 0x7F) << 8) | str[1]);
		// copy buff to user if spi transfer
		if (retries < 20) {
			if (copy_to_user(buff, str, count)) {
				ret = -EFAULT;
				goto out;
			}
		}

		if (unlikely(retries == 20)) {
			NVT_ERR("error, ret = %d\n", ret);
			ret = -EIO;
			goto out;
		}
	} else {
		NVT_ERR("Call error, str[0]=%d\n", str[0]);
		ret = -EFAULT;
		goto out;
	}

out:
	kfree(str);
	kfree(buf);
kzalloc_failed:
	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen /proc/NVTSPI open function.

return:
	Executive outcomes. 0---succeed. -12---failed.
*******************************************************/
static int32_t nvt_flash_open(struct inode *inode, struct file *file)
{
	struct nvt_flash_data *dev;

	dev = kmalloc(sizeof(struct nvt_flash_data), GFP_KERNEL);
	if (dev == NULL) {
		NVT_ERR("Failed to allocate memory for nvt flash data\n");
		return -ENOMEM;
	}

	rwlock_init(&dev->lock);
	file->private_data = dev;

	return 0;
}

/*******************************************************
Description:
	Novatek touchscreen /proc/NVTSPI close function.

return:
	Executive outcomes. 0---succeed.
*******************************************************/
static int32_t nvt_flash_close(struct inode *inode, struct file *file)
{
	struct nvt_flash_data *dev = file->private_data;

	if (dev)
		kfree(dev);

	return 0;
}

#ifdef HAVE_PROC_OPS
static const struct proc_ops nvt_flash_fops = {
	.proc_open = nvt_flash_open,
	.proc_release = nvt_flash_close,
	.proc_read = nvt_flash_read,
};
#else
static const struct file_operations nvt_flash_fops = {
	.owner = THIS_MODULE,
	.open = nvt_flash_open,
	.release = nvt_flash_close,
	.read = nvt_flash_read,
};
#endif

/*******************************************************
Description:
	Novatek touchscreen /proc/NVTSPI initial function.

return:
	Executive outcomes. 0---succeed. -12---failed.
*******************************************************/
static int32_t nvt_flash_proc_init(void)
{
	NVT_proc_entry = proc_create(DEVICE_NAME, 0444, NULL, &nvt_flash_fops);
	if (NVT_proc_entry == NULL) {
		NVT_ERR("Failed!\n");
		return -ENOMEM;
	} else {
		NVT_LOG("Succeeded!\n");
	}

	NVT_LOG("============================================================\n");
	NVT_LOG("Create /proc/%s\n", DEVICE_NAME);
	NVT_LOG("============================================================\n");

	return 0;
}

/*******************************************************
Description:
	Novatek touchscreen /proc/NVTSPI deinitial function.

return:
	n.a.
*******************************************************/
static void nvt_flash_proc_deinit(void)
{
	if (NVT_proc_entry != NULL) {
		remove_proc_entry(DEVICE_NAME, NULL);
		NVT_proc_entry = NULL;
		NVT_LOG("Removed /proc/%s\n", DEVICE_NAME);
	}
}
#endif

#if WAKEUP_GESTURE
#define GESTURE_WORD_C 12
#define GESTURE_WORD_W 13
#define GESTURE_WORD_V 14
#define GESTURE_DOUBLE_CLICK 15
#define GESTURE_WORD_Z 16
#define GESTURE_WORD_M 17
#define GESTURE_WORD_O 18
#define GESTURE_WORD_e 19
#define GESTURE_WORD_S 20
#define GESTURE_SLIDE_UP 21
#define GESTURE_SLIDE_DOWN 22
#define GESTURE_SLIDE_LEFT 23
#define GESTURE_SLIDE_RIGHT 24
/* customized gesture id */
#define DATA_PROTOCOL 30

/* function page definition */
#define FUNCPAGE_GESTURE 1

/*******************************************************
Description:
	Novatek touchscreen wake up gesture key report function.

return:
	n.a.
*******************************************************/
void nvt_ts_wakeup_gesture_report(uint8_t gesture_id, uint8_t *data)
{
	uint32_t keycode = 0;
	uint8_t func_type = data[2];
	uint8_t func_id = data[3];

	/* support fw specifal data protocol */
	if ((gesture_id == DATA_PROTOCOL) && (func_type == FUNCPAGE_GESTURE)) {
		gesture_id = func_id;
	} else if (gesture_id > DATA_PROTOCOL) {
		NVT_ERR("gesture_id %d is invalid, func_type=%d, func_id=%d\n",
			gesture_id, func_type, func_id);
		return;
	}

	NVT_LOG("gesture_id = %d\n", gesture_id);

	switch (gesture_id) {
	case GESTURE_WORD_C:
		NVT_LOG("Gesture : Word-C.\n");
		keycode = gesture_key_array[0];
		break;
	case GESTURE_WORD_W:
		NVT_LOG("Gesture : Word-W.\n");
		keycode = gesture_key_array[1];
		break;
	case GESTURE_WORD_V:
		NVT_LOG("Gesture : Word-V.\n");
		keycode = gesture_key_array[2];
		break;
	case GESTURE_DOUBLE_CLICK:
		NVT_LOG("Gesture : Double Click.\n");
		keycode = gesture_key_array[3];
		break;
	case GESTURE_WORD_Z:
		NVT_LOG("Gesture : Word-Z.\n");
		keycode = gesture_key_array[4];
		break;
	case GESTURE_WORD_M:
		NVT_LOG("Gesture : Word-M.\n");
		keycode = gesture_key_array[5];
		break;
	case GESTURE_WORD_O:
		NVT_LOG("Gesture : Word-O.\n");
		keycode = gesture_key_array[6];
		break;
	case GESTURE_WORD_e:
		NVT_LOG("Gesture : Word-e.\n");
		keycode = gesture_key_array[7];
		break;
	case GESTURE_WORD_S:
		NVT_LOG("Gesture : Word-S.\n");
		keycode = gesture_key_array[8];
		break;
	case GESTURE_SLIDE_UP:
		NVT_LOG("Gesture : Slide UP.\n");
		keycode = gesture_key_array[9];
		break;
	case GESTURE_SLIDE_DOWN:
		NVT_LOG("Gesture : Slide DOWN.\n");
		keycode = gesture_key_array[10];
		break;
	case GESTURE_SLIDE_LEFT:
		NVT_LOG("Gesture : Slide LEFT.\n");
		keycode = gesture_key_array[11];
		break;
	case GESTURE_SLIDE_RIGHT:
		NVT_LOG("Gesture : Slide RIGHT.\n");
		keycode = gesture_key_array[12];
		break;
	default:
		break;
	}

	if (keycode > 0) {
		input_report_key(ts->input_dev, keycode, 1);
		input_sync(ts->input_dev);
		input_report_key(ts->input_dev, keycode, 0);
		input_sync(ts->input_dev);
	}
}
#endif

/*******************************************************
Description:
	Novatek touchscreen set charger flag function.
	If insert usb charger called nvt_set_charger(USB_DETECT_IN)
	Otherwise called nvt_set_charger(USB_DETECT_OUT)
return:
	n.a.
*******************************************************/
/*

#define USB_DETECT_IN 1
#define USB_DETECT_OUT 0
#define CMD_CHARGER_ON (0x53)
#define CMD_CHARGER_OFF (0x51)
int32_t nvt_set_charger(uint8_t charger_on_off)
{
	uint8_t buf[8] = { 0 };
	int32_t ret = 0;

	NVT_LOG("set charger: %d\n", charger_on_off);

	msleep(20);

	mutex_lock(&ts->lock);
	//---set xdata index to EVENT BUF ADDR---
	ret = nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_HOST_CMD);
	if (ret < 0) {
		NVT_ERR("Set event buffer index fail!\n");
		goto nvt_set_charger_out;
	}

	if (charger_on_off == USB_DETECT_IN) {
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = CMD_CHARGER_ON;
		ret = CTP_SPI_WRITE(ts->client, buf, 2);
		if (ret < 0) {
			NVT_ERR("Write set charger command fail!\n");
			goto nvt_set_charger_out;
		} else {
			NVT_LOG("set charger on cmd succeeded\n");
		}
	} else if (charger_on_off == USB_DETECT_OUT) {
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = CMD_CHARGER_OFF;
		ret = CTP_SPI_WRITE(ts->client, buf, 2);
		if (ret < 0) {
			NVT_ERR("Write set charger command fail!\n");
			goto nvt_set_charger_out;
		} else {
			NVT_LOG("set charger off cmd succeeded\n");
		}
	} else {
		NVT_ERR("Invalid charger parameter!\n");
		ret = -EINVAL;
	}

nvt_set_charger_out:

	mutex_unlock(&ts->lock);

	return ret;
}
EXPORT_SYMBOL(nvt_set_charger);
*/

/*******************************************************
Description:
	Novatek touchscreen parse device tree function.

return:
	n.a.
*******************************************************/
#ifdef CONFIG_OF
static int32_t nvt_parse_dt(struct device *dev)
{
	struct device_node *np = dev->of_node;
	int32_t ret = 0;

	/*
	 * TB710FU port: this GKI tree dropped linux/of_gpio.h and
	 * of_get_named_gpio_flags().  The vendor driver only wants the raw
	 * gpio *number* (it uses the legacy gpio_request API later), so parse
	 * the "<phandle gpio flags>" specifier by hand and return cell 1.
	 */
#define nvt_of_get_named_gpio(np, prop)					\
	({								\
		u32 nvt_spec[2] = { 0, 0 };				\
		int nvt_ret = of_property_read_u32_array(np, prop,	\
							nvt_spec, 2);	\
		nvt_ret ? nvt_ret : (int)nvt_spec[1];			\
	})

#if NVT_TOUCH_SUPPORT_HW_RST
	ts->reset_gpio = nvt_of_get_named_gpio(np, "novatek,reset-gpio");
	NVT_LOG("novatek,reset-gpio=%d\n", ts->reset_gpio);
#endif
	ts->irq_gpio = nvt_of_get_named_gpio(np, "novatek,irq-gpio");
	NVT_LOG("novatek,irq-gpio=%d\n", ts->irq_gpio);

	ts->pen_support = of_property_read_bool(np, "novatek,pen-support");
	NVT_LOG("novatek,pen-support=%d\n", ts->pen_support);

	ret = of_property_read_u32(np, "novatek,spi-rd-fast-addr",
				   &SPI_RD_FAST_ADDR);
	if (ret) {
		NVT_LOG("not support novatek,spi-rd-fast-addr\n");
		SPI_RD_FAST_ADDR = 0;
		ret = 0;
	} else {
		NVT_LOG("SPI_RD_FAST_ADDR=0x%06X\n", SPI_RD_FAST_ADDR);
	}

	return ret;
}
#else
static int32_t nvt_parse_dt(struct device *dev)
{
#if NVT_TOUCH_SUPPORT_HW_RST
	ts->reset_gpio = NVTTOUCH_RST_PIN;
#endif
	ts->irq_gpio = NVTTOUCH_INT_PIN;
	ts->pen_support = false;
	return 0;
}
#endif

/* TB710FU: the INT trigger is not discoverable from this board's DTS (the
 * vendor flags cell of "novatek,irq-gpio" holds gpio flags, not an irq
 * type), so keep the vendor default adjustable at runtime - reloading the
 * module beats flashing a new DTB while the polarity is being verified. */
static int nvt_int_trigger = INT_TRIGGER_TYPE;
module_param_named(int_trigger, nvt_int_trigger, int, 0644);
MODULE_PARM_DESC(int_trigger, "INT pad trigger type (default IRQ_TYPE_EDGE_RISING)");

#if IS_ENABLED(CONFIG_OF)
/*******************************************************
Description:
	Resolve the interrupt from the vendor "novatek,irq-gpio" specifier.

	The legacy gpio API the vendor driver uses is unusable here (no
	exported of_get_named_gpio(), and gpio_to_desc() returns NULL for
	every legacy number), so go through the GPIO controller's irq
	domain - the same mapping the standard "interrupts" binding makes.

return:
	irq number (>0) or negative errno.
*******************************************************/
static int32_t nvt_irq_from_dt(struct device *dev)
{
	struct of_phandle_args args;
	int32_t irq, ret;

	ret = of_parse_phandle_with_args(dev->of_node, "novatek,irq-gpio",
									 "#gpio-cells", 0, &args);
	if (ret)
		return ret;
	if (args.args_count != 2) {
		of_node_put(args.np);
		return -EINVAL;
	}
	/* the flags cell is a gpio flag (0x2001); keep only the sense bits */
	args.args[1] &= IRQ_TYPE_SENSE_MASK;

	irq = irq_create_of_mapping(&args);
	of_node_put(args.np);

	return irq;
}
#else
static int32_t nvt_irq_from_dt(struct device *dev) { return -ENODEV; }
#endif

/*******************************************************
Description:
	Novatek touchscreen config and request gpio

return:
	Executive outcomes. 0---succeed. not 0---failed.
*******************************************************/
static int nvt_gpio_config(struct nvt_ts_data *ts)
{
	int32_t ret = 0;

#if NVT_TOUCH_SUPPORT_HW_RST
	/*
	 * request RST-pin (Output/Low; raised after nvt_eng_reset())
	 *
	 * TB710FU: the legacy gpio_request_one() path returns -EPROBE_DEFER for
	 * this line whatever global number is used, so take it through the
	 * descriptor API and convert back with desc_to_gpio() - the rest of the
	 * driver keeps using gpio_set_value() on the number.  RESX has to be a
	 * real low->high pulse once the rail is up, which is why HW_RST stays 1.
	 */
	{
		struct gpio_desc *rst;

		rst = fwnode_gpiod_get_index(of_fwnode_handle(ts->client->dev.of_node),
					     "novatek-reset", 0,
					     GPIOD_OUT_LOW, "NVT-tp-rst");
		if (IS_ERR(rst)) {
			ret = PTR_ERR(rst);
			NVT_ERR("Failed to get NVT-tp-rst GPIO ret=%d\n", ret);
			goto err_request_reset_gpio;
		}
		ts->reset_gpio = desc_to_gpio(rst);
		ts->reset_desc = rst;
		NVT_LOG("NVT-tp-rst gpio=%d\n", ts->reset_gpio);
	}
#endif

	/* INT is claimed as an interrupt resource by the irq core when
	 * nvt_ts_probe() maps it in nvt_irq_from_dt(). */

	return ret;

#if NVT_TOUCH_SUPPORT_HW_RST
err_request_reset_gpio:
#endif
	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen deconfig gpio

return:
	n.a.
*******************************************************/
static void nvt_gpio_deconfig(struct nvt_ts_data *ts)
{
	if (gpio_is_valid(ts->irq_gpio))
		gpio_free(ts->irq_gpio);
#if NVT_TOUCH_SUPPORT_HW_RST
	/* RESX came from fwnode_gpiod_get_index(), so it must be
	 * released with gpiod_put(): gpio_free() on the legacy number
	 * is a no-op and the request leaked, making every later probe
	 * fail with -EBUSY. */
	if (ts->reset_desc) {
		gpiod_put(ts->reset_desc);
		ts->reset_desc = NULL;
	}
	ts->reset_gpio = -EINVAL;
#endif
}

static uint8_t nvt_fw_recovery(uint8_t *point_data)
{
	uint8_t i = 0;
	uint8_t detected = true;

	/* check pattern */
	for (i = 1; i < 7; i++) {
		if (point_data[i] != 0x77) {
			detected = false;
			break;
		}
	}

	return detected;
}

#if NVT_TOUCH_ESD_PROTECT
void nvt_esd_check_enable(uint8_t enable)
{
	/* update interrupt timer */
	irq_timer = jiffies;
	/* clear esd_retry counter, if protect function is enabled */
	esd_retry = enable ? 0 : esd_retry;
	/* enable/disable esd check flag */
	esd_check = enable;
}

static void nvt_esd_check_func(struct work_struct *work)
{
	unsigned int timer = jiffies_to_msecs(jiffies - irq_timer);

	//NVT_LOG("esd_check = %d (retry %d)\n", esd_check, esd_retry);	//DEBUG

	if ((timer > NVT_TOUCH_ESD_CHECK_PERIOD) && esd_check) {
		mutex_lock(&ts->lock);
		NVT_ERR("do ESD recovery, timer = %d, retry = %d\n", timer,
			esd_retry);
		/* do esd recovery, reload fw */
		nvt_update_firmware(BOOT_UPDATE_FIRMWARE_NAME);
		mutex_unlock(&ts->lock);
		/* update interrupt timer */
		irq_timer = jiffies;
		/* update esd_retry counter */
		esd_retry++;
	}

	queue_delayed_work(nvt_esd_check_wq, &nvt_esd_check_work,
			   msecs_to_jiffies(NVT_TOUCH_ESD_CHECK_PERIOD));
}
#endif /* #if NVT_TOUCH_ESD_PROTECT */

#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
static int hall_status = 1;
static int nvt_hall_pm = 0;
static int nvt_hall_pm_status = 0;
static void nvt_hall_check_func(struct work_struct *work)
{
       uint8_t buf[4] = {0};
       int hall_work_status = -1;
       static int timer0 = 0;
       unsigned int timer = jiffies_to_msecs(jiffies - timer0);
       hall_work_status = gpio_get_value(501);
       if(bTouchIsAwake == 0){
               if ((timer > NVT_HALL_WORK_DELAY) && (hall_status != hall_work_status)) {
                       if (ts->dev_pm_suspend == true) {
                               nvt_hall_pm = 1;
                               NVT_LOG("The status of pm is suspend");
                       } else {
                               if (nvt_hall_pm_status == 1) {
                                       NVT_LOG("The status of double click has changed");
                                       hall_status = 0;
                               } else if (hall_work_status == 0){
                                       NVT_LOG("The keyboard close!");
                                       buf[0] = EVENT_MAP_HOST_CMD;
                                       buf[1] = 0x11;
                                       CTP_SPI_WRITE(ts->client, buf, 2);
                                       hall_status = 0;
                                       timer0 = jiffies;
                               } else {
                                       NVT_LOG("The keyboard open!");
                                       hall_status = 1;
                               }
                       }
               }
       }

       queue_delayed_work(nvt_hall_check_wq, &nvt_hall_check_work,
                       msecs_to_jiffies(NVT_HALL_WORK_DELAY));
}
#endif
#endif

#define PEN_DATA_LEN 14
#if CHECK_PEN_DATA_CHECKSUM
static int32_t nvt_ts_pen_data_checksum(uint8_t *buf, uint8_t length)
{
	uint8_t checksum = 0;
	int32_t i = 0;

	// Calculate checksum
	for (i = 0; i < length - 1; i++) {
		checksum += buf[i];
	}
	checksum = (~checksum + 1);

	// Compare ckecksum and dump fail data
	if (checksum != buf[length - 1]) {
		NVT_ERR("pen packet checksum not match. (buf[%d]=0x%02X, checksum=0x%02X)\n",
			length - 1, buf[length - 1], checksum);
		//--- dump pen buf ---
		for (i = 0; i < length; i++) {
			printk("%02X ", buf[i]);
		}
		printk("\n");

		return -1;
	}

	return 0;
}
#endif // #if CHECK_PEN_DATA_CHECKSUM

#if NVT_TOUCH_WDT_RECOVERY
static uint8_t recovery_cnt = 0;
static uint8_t nvt_wdt_fw_recovery(uint8_t *point_data)
{
	uint32_t recovery_cnt_max = 10;
	uint8_t recovery_enable = false;
	uint8_t i = 0;

	recovery_cnt++;

	/* check pattern */
	for (i = 1; i < 7; i++) {
		if ((point_data[i] != 0xFD) && (point_data[i] != 0xFE)) {
			recovery_cnt = 0;
			break;
		}
	}

	if (recovery_cnt > recovery_cnt_max) {
		recovery_enable = true;
		recovery_cnt = 0;
	}

	return recovery_enable;
}

void nvt_clear_aci_error_flag(void)
{
	if (ts->mmap->ACI_ERR_CLR_ADDR == 0)
		return;

	nvt_write_addr(ts->mmap->ACI_ERR_CLR_ADDR, 0xA5);

	nvt_set_page(ts->mmap->EVENT_BUF_ADDR);
}
#endif /* #if NVT_TOUCH_WDT_RECOVERY */

void nvt_read_fw_history(uint32_t fw_history_addr)
{
	uint8_t i = 0;
	uint8_t buf[65];
	char str[128];

	if (fw_history_addr == 0)
		return;

	nvt_set_page(fw_history_addr);

	buf[0] = (uint8_t)(fw_history_addr & 0x7F);
	CTP_SPI_READ(ts->client, buf, 64 + 1); //read 64bytes history

	//print all data
	NVT_LOG("fw history 0x%X: \n", fw_history_addr);
	for (i = 0; i < 4; i++) {
		snprintf(str, sizeof(str),
			 "%02X %02X %02X %02X %02X %02X %02X %02X  "
			 "%02X %02X %02X %02X %02X %02X %02X %02X\n",
			 buf[1 + i * 16], buf[2 + i * 16], buf[3 + i * 16],
			 buf[4 + i * 16], buf[5 + i * 16], buf[6 + i * 16],
			 buf[7 + i * 16], buf[8 + i * 16], buf[9 + i * 16],
			 buf[10 + i * 16], buf[11 + i * 16], buf[12 + i * 16],
			 buf[13 + i * 16], buf[14 + i * 16], buf[15 + i * 16],
			 buf[16 + i * 16]);
		NVT_LOG("%s", str);
	}

	nvt_set_page(ts->mmap->EVENT_BUF_ADDR);
}

void nvt_read_fw_history_all(void)
{
	/* ICM History */
	nvt_read_fw_history(ts->mmap->MMAP_HISTORY_EVENT0);
	nvt_read_fw_history(ts->mmap->MMAP_HISTORY_EVENT1);

	/* ICS History */
	if (ts->is_cascade) {
		nvt_read_fw_history(ts->mmap->MMAP_HISTORY_EVENT0_ICS);
		nvt_read_fw_history(ts->mmap->MMAP_HISTORY_EVENT1_ICS);
	}
}

#if POINT_DATA_CHECKSUM
static int32_t nvt_ts_point_data_checksum(uint8_t *buf, uint8_t length)
{
	uint8_t checksum = 0;
	int32_t i = 0;

	// Generate checksum
	for (i = 0; i < length - 1; i++) {
		checksum += buf[i + 1];
	}
	checksum = (~checksum + 1);

	// Compare ckecksum and dump fail data
	if (checksum != buf[length]) {
		NVT_ERR("i2c/spi packet checksum not match. (point_data[%d]=0x%02X, checksum=0x%02X)\n",
			length, buf[length], checksum);

		for (i = 0; i < 10; i++) {
			NVT_LOG("%02X %02X %02X %02X %02X %02X\n",
				buf[1 + i * 6], buf[2 + i * 6], buf[3 + i * 6],
				buf[4 + i * 6], buf[5 + i * 6], buf[6 + i * 6]);
		}

		NVT_LOG("%02X %02X %02X %02X %02X\n", buf[61], buf[62], buf[63],
			buf[64], buf[65]);

		return -1;
	}

	return 0;
}
#endif /* POINT_DATA_CHECKSUM */

#if NVT_DPR_SWITCH
#define KEY_SKIN_STYLUS       0xF9//606
#define FUNCPAGE_STYLUS 5
#define LEAVE_PEN_MODE 0
#define DETECT_PEN 1
#define ENTER_PEN_MODE 2
int32_t nvt_check_stylus_state(uint8_t input_id, uint8_t *data)
{
	int32_t ret = 0;
	uint8_t func_type = data[2];
	uint8_t stylus_state = data[3];

	if ((input_id == DATA_PROTOCOL) && (func_type == FUNCPAGE_STYLUS)) {
		ret = stylus_state;
		if (stylus_state == DETECT_PEN) {
			NVT_LOG("Enter stylus mode\n");
            input_report_key(ts->input_dev, KEY_SKIN_STYLUS, 1);
            input_sync(ts->input_dev);
            input_report_key(ts->input_dev, KEY_SKIN_STYLUS, 0);
            input_sync(ts->input_dev);
			ret = 1;
		} else if (stylus_state == ENTER_PEN_MODE) {
			ts->fw_pen_state = 1;
			NVT_LOG("Enter PEN mode\n");
			ret = 1;
		} else if (stylus_state == LEAVE_PEN_MODE) {
			ts->fw_pen_state = 0;
			NVT_LOG("Leave PEN mode\n");
			ret = 1;
		} else {
			NVT_ERR("invalid state %d!\n", stylus_state);
			ret = -1;
		}
	}

	return ret;
}
#endif

#ifdef BUILD_LAPIS_TOUCH
uint8_t touch_info;
static uint8_t touch_info_pre;
#endif

#if REPORT_PEN_MAC_ADDR
static uint8_t pen_mac_addr[6]={0};
static uint8_t pen_mac_addr_pre[6]={0};
#endif

/*******************************************************
Description:
	Novatek touchscreen work function.

return:
	n.a.
*******************************************************/
uint32_t pen_battery = 0;
static irqreturn_t nvt_ts_work_func(int irq, void *data)
{
	int32_t ret = -1;
	uint8_t point_data[POINT_DATA_LEN + PEN_DATA_LEN + 1 + DUMMY_BYTES] = {
		0
	};
	uint32_t position = 0;
	uint32_t input_x = 0;
	uint32_t input_y = 0;
	uint32_t input_w = 0;
	uint32_t input_p = 0;
	uint8_t input_id = 0;
#if MT_PROTOCOL_B
	uint8_t press_id[TOUCH_MAX_FINGER_NUM] = { 0 };
#endif /* MT_PROTOCOL_B */
	int32_t i = 0;
	int32_t finger_cnt = 0;
	uint8_t pen_format_id = 0;
	uint32_t pen_x = 0;
	uint32_t pen_y = 0;
	uint32_t pen_pressure = 0;
	uint32_t pen_distance = 0;
	int8_t pen_tilt_x = 0;
	int8_t pen_tilt_y = 0;
	uint32_t pen_btn1 = 0;
	uint32_t pen_btn2 = 0;
	u16 frame_time = 0;
	struct lenovo_pen_info *ppen_info;

#if NVT_CUST_PROC_CMD
	uint8_t wdt_recovery = false;
#endif

#if WAKEUP_GESTURE
	if (bTouchIsAwake == 0) {
		pm_wakeup_event(&ts->client->dev, 5000);
	}
#endif

	mutex_lock(&ts->lock);

#if NVT_PM_WAIT_BUS_RESUME_COMPLETE
	if (ts->dev_pm_suspend) {
		ret = wait_for_completion_timeout(&ts->dev_pm_resume_completion,
						  msecs_to_jiffies(500));
		if (!ret) {
			NVT_ERR("system(bus) can't finished resuming procedure, skip it!\n");
			goto XFER_ERROR;
		}
	}
#endif /* NVT_PM_WAIT_BUS_RESUME_COMPLETE */

#if NVT_SUPER_RESOLUTION_N
	ret = CTP_SPI_READ(ts->client, point_data, POINT_DATA_LEN + 1);
#else /* #if NVT_SUPER_RESOLUTION_N */
	if (ts->pen_support)
		ret = CTP_SPI_READ(ts->client, point_data,
				   POINT_DATA_LEN + PEN_DATA_LEN + 1);
	else
		ret = CTP_SPI_READ(ts->client, point_data, POINT_DATA_LEN + 1);
#endif /* #if NVT_SUPER_RESOLUTION_N */
	if (ret < 0) {
		NVT_ERR("CTP_SPI_READ failed.(%d)\n", ret);
		goto XFER_ERROR;
	}
	/*
	//--- dump SPI buf ---
	for (i = 0; i < 10; i++) {
		printk("%02X %02X %02X %02X %02X %02X  ",
			point_data[1+i*6], point_data[2+i*6], point_data[3+i*6], point_data[4+i*6], point_data[5+i*6], point_data[6+i*6]);
	}
	printk("\n");
*/

#if NVT_TOUCH_WDT_RECOVERY
	/* ESD protect by WDT */
	if (nvt_wdt_fw_recovery(point_data)) {
		NVT_ERR("Recover for fw reset, %02X\n", point_data[1]);
		if (point_data[1] == 0xFE) {
			nvt_sw_reset_idle();
			nvt_clear_aci_error_flag();
		}
		nvt_read_fw_history_all();
		nvt_update_firmware(BOOT_UPDATE_FIRMWARE_NAME);
		nvt_read_fw_history_all();
#if NVT_CUST_PROC_CMD
		wdt_recovery = true;
#endif
		goto XFER_ERROR;
	}
#endif /* #if NVT_TOUCH_WDT_RECOVERY */

	/* ESD protect by FW handshake */
	if (nvt_fw_recovery(point_data)) {
#if NVT_TOUCH_ESD_PROTECT
		nvt_esd_check_enable(true);
#endif /* #if NVT_TOUCH_ESD_PROTECT */
		goto XFER_ERROR;
	}

#if POINT_DATA_CHECKSUM
	if (POINT_DATA_LEN >= POINT_DATA_CHECKSUM_LEN) {
		ret = nvt_ts_point_data_checksum(point_data,
						 POINT_DATA_CHECKSUM_LEN);
		if (ret) {
			goto XFER_ERROR;
		}
	}
#endif /* POINT_DATA_CHECKSUM */

#if NVT_DPR_SWITCH
	input_id = (uint8_t)(point_data[1] >> 3);
	if (nvt_check_stylus_state(input_id, point_data)) {
		goto XFER_ERROR; /* to skip point data parsing */
	}
#endif

#if WAKEUP_GESTURE
	if (bTouchIsAwake == 0) {
		input_id = (uint8_t)(point_data[1] >> 3);
		nvt_ts_wakeup_gesture_report(input_id, point_data);
		mutex_unlock(&ts->lock);
		return IRQ_HANDLED;
	}
#endif

	finger_cnt = 0;

	for (i = 0; i < ts->max_touch_num; i++) {
		position = 1 + 6 * i;
		input_id = (uint8_t)(point_data[position + 0] >> 3);
		if ((input_id == 0) || (input_id > ts->max_touch_num))
			continue;

		if (((point_data[position] & 0x07) == 0x01) ||
		    ((point_data[position] & 0x07) ==
		     0x02)) { //finger down (enter & moving)
#if NVT_DPR_SWITCH
			ts->finger_event_flag = true;
#endif

#if NVT_TOUCH_ESD_PROTECT
			/* update interrupt timer */
			irq_timer = jiffies;
#endif /* #if NVT_TOUCH_ESD_PROTECT */
#if NVT_SUPER_RESOLUTION_N
			input_x = (uint32_t)(point_data[position + 1] << 8) +
				  (uint32_t)(point_data[position + 2]);
			input_y = (uint32_t)(point_data[position + 3] << 8) +
				  (uint32_t)(point_data[position + 4]);
			if ((input_x > TOUCH_MAX_WIDTH) ||
			    (input_y > TOUCH_MAX_HEIGHT))
				continue;
			input_w = (uint32_t)(point_data[position + 5]);
			if (input_w == 0)
				input_w = 1;
			input_p = (uint32_t)(point_data[1 + 98 + i]);
			if (input_p == 0)
				input_p = 1;
#else /* #if NVT_SUPER_RESOLUTION_N */
			input_x = (uint32_t)(point_data[position + 1] << 4) +
				  (uint32_t)(point_data[position + 3] >> 4);
			input_y = (uint32_t)(point_data[position + 2] << 4) +
				  (uint32_t)(point_data[position + 3] & 0x0F);
			if ((input_x > TOUCH_MAX_WIDTH) ||
			    (input_y > TOUCH_MAX_HEIGHT))
				continue;
			input_w = (uint32_t)(point_data[position + 4]);
			if (input_w == 0)
				input_w = 1;
			if (i < 2) {
				input_p = (uint32_t)(point_data[position + 5]) +
					  (uint32_t)(point_data[i + 63] << 8);
				if (input_p > TOUCH_FORCE_NUM)
					input_p = TOUCH_FORCE_NUM;
			} else {
				input_p = (uint32_t)(point_data[position + 5]);
			}
			if (input_p == 0)
				input_p = 1;
#endif /* #if NVT_SUPER_RESOLUTION_N */

#if MT_PROTOCOL_B
			press_id[input_id - 1] = 1;
			input_mt_slot(ts->input_dev, input_id - 1);
			input_mt_report_slot_state(ts->input_dev,
						   MT_TOOL_FINGER, true);
#else /* MT_PROTOCOL_B */
			input_report_abs(ts->input_dev, ABS_MT_TRACKING_ID,
					 input_id - 1);
			input_report_key(ts->input_dev, BTN_TOUCH, 1);
#endif /* MT_PROTOCOL_B */

			input_report_abs(ts->input_dev, ABS_MT_POSITION_X,
					 input_x);
			input_report_abs(ts->input_dev, ABS_MT_POSITION_Y,
					 input_y);
			input_report_abs(ts->input_dev, ABS_MT_TOUCH_MAJOR,
					 input_w);
//			input_report_abs(ts->input_dev, ABS_MT_PRESSURE,
//					 input_p);
            input_report_abs(ts->input_dev, ABS_MT_PRESSURE, TOUCH_FORCE_NUM);

#if MT_PROTOCOL_B
#else /* MT_PROTOCOL_B */
			input_mt_sync(ts->input_dev);
#endif /* MT_PROTOCOL_B */

			finger_cnt++;
		}
	}

#if MT_PROTOCOL_B
	for (i = 0; i < ts->max_touch_num; i++) {
		if (press_id[i] != 1) {
			input_mt_slot(ts->input_dev, i);
			input_report_abs(ts->input_dev, ABS_MT_TOUCH_MAJOR, 0);
			input_report_abs(ts->input_dev, ABS_MT_PRESSURE, 0);
			input_mt_report_slot_state(ts->input_dev,
						   MT_TOOL_FINGER, false);
		}
	}

	input_report_key(ts->input_dev, BTN_TOUCH, (finger_cnt > 0));

#if NVT_DPR_SWITCH
	if(finger_cnt == 0) {
		ts->finger_event_flag = false;
	}
#endif

#else /* MT_PROTOCOL_B */
	if (finger_cnt == 0) {
		input_report_key(ts->input_dev, BTN_TOUCH, 0);
		input_mt_sync(ts->input_dev);
	}

#if NVT_DPR_SWITCH
		ts->finger_event_flag = false;
#endif

#endif /* MT_PROTOCOL_B */

#if TOUCH_KEY_NUM > 0
	if (point_data[61] == 0xF8) {
#if NVT_TOUCH_ESD_PROTECT
		/* update interrupt timer */
		irq_timer = jiffies;
#endif /* #if NVT_TOUCH_ESD_PROTECT */
		for (i = 0; i < ts->max_button_num; i++) {
			input_report_key(ts->input_dev, touch_key_array[i],
					 ((point_data[62] >> i) & 0x01));
		}
	} else {
		for (i = 0; i < ts->max_button_num; i++) {
			input_report_key(ts->input_dev, touch_key_array[i], 0);
		}
	}
#endif

	input_sync(ts->input_dev);

	if (ts->pen_support) {
/*
		//--- dump pen buf ---
		printk("%02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X\n",
			point_data[66], point_data[67], point_data[68], point_data[69], point_data[70],
			point_data[71], point_data[72], point_data[73], point_data[74], point_data[75],
			point_data[76], point_data[77], point_data[78], point_data[79]);
*/
#if CHECK_PEN_DATA_CHECKSUM
		if (nvt_ts_pen_data_checksum(&point_data[66], PEN_DATA_LEN)) {
			// pen data packet checksum not match, skip it
			goto XFER_ERROR;
		}
#endif // #if CHECK_PEN_DATA_CHECKSUM

		// parse and handle pen report
		pen_format_id = point_data[66];
		if (pen_format_id != 0xFF) {
			if (pen_format_id == 0x01) {
#if NVT_DPR_SWITCH
				ts->stylus_event_flag = true;
#endif
				// report pen data
				pen_x = (uint32_t)(point_data[67] << 8) +
					(uint32_t)(point_data[68]);
				pen_y = (uint32_t)(point_data[69] << 8) +
					(uint32_t)(point_data[70]);
				if ((pen_x > PEN_MAX_WIDTH) ||
				    (pen_y > PEN_MAX_HEIGHT))
					goto XFER_ERROR;
				pen_pressure = (uint32_t)(point_data[71] << 8) +
					       (uint32_t)(point_data[72]);
				pen_tilt_x = (int32_t)point_data[73];
				pen_tilt_y = (int32_t)point_data[74];
				pen_distance = (uint32_t)(point_data[75] << 8) +
					       (uint32_t)(point_data[76]);
				pen_btn1 = (uint32_t)(point_data[77] & 0x01);
				pen_btn2 = (uint32_t)((point_data[77] >> 1) &
						      0x01);
#ifdef BUILD_LAPIS_TOUCH
				touch_info = (point_data[77] >> 2) & 0x3F;
#endif
				pen_battery = (uint32_t)point_data[78];
				//				printk("x=%d,y=%d,p=%d,tx=%d,ty=%d,d=%d,b1=%d,b2=%d,bat=%d\n", pen_x, pen_y, pen_pressure,
				//						pen_tilt_x, pen_tilt_y, pen_distance, pen_btn1, pen_btn2, pen_battery);

				input_report_abs(ts->pen_input_dev, ABS_X,
						 pen_x);
				input_report_abs(ts->pen_input_dev, ABS_Y,
						 pen_y);
				input_report_abs(ts->pen_input_dev,
						 ABS_PRESSURE, pen_pressure);
				input_report_key(ts->pen_input_dev, BTN_TOUCH,
						 !!pen_pressure);
				input_report_abs(ts->pen_input_dev, ABS_TILT_X,
						 pen_tilt_x);
				input_report_abs(ts->pen_input_dev, ABS_TILT_Y,
						 pen_tilt_y);
				input_report_abs(ts->pen_input_dev,
						 ABS_DISTANCE, pen_distance);
				input_report_key(
					ts->pen_input_dev, BTN_TOOL_PEN,
					!!pen_distance || !!pen_pressure);
				input_report_key(ts->pen_input_dev, BTN_STYLUS,
						 pen_btn1);
				input_report_key(ts->pen_input_dev, BTN_STYLUS2,
						 pen_btn2);
				// TBD: pen battery event report
				// NVT_LOG("pen_battery=%d\n", pen_battery);

				// ioctl-DAA Buffering pen raw data
				frame_time = (u16)jiffies_to_msecs(jiffies);
				ppen_info  = (struct lenovo_pen_info *)&pen_buffer[0];
				ppen_info += pen_buffer_wp;
				memset(ppen_info, 0, sizeof(struct lenovo_pen_info));
				ppen_info->coords.status = 1;
				ppen_info->coords.tool_type = DATA_TYPE_RAW;
				ppen_info->coords.tilt_x = pen_tilt_x;
				ppen_info->coords.tilt_y = pen_tilt_y;
				ppen_info->coords.x = pen_x/10;
				ppen_info->coords.y = pen_y/10;
				ppen_info->coords.p = pen_pressure;
				ppen_info->frame_no = pen_frame_no;
				ppen_info->frame_t = frame_time;
				ppen_info->data_type = DATA_TYPE_RAW;
				pen_frame_no++;
				if(MAX_IO_CONTROL_REPORT > pen_report_num) {    // Max count: MAX_IO_CONTROL_REPORT
					pen_report_num++;
				}
				pen_buffer_wp++;
				if(LENOVO_MAX_BUFFER == pen_buffer_wp) {
					pen_buffer_wp = 0;
				}
#ifdef BUILD_LAPIS_TOUCH
				//report Touch infomation
				if(touch_info != touch_info_pre){
					kobject_uevent(&nvt_ts_pdev->dev.kobj,KOBJ_CHANGE);
					touch_info_pre = touch_info;
				}
#endif
			} else if (pen_format_id == 0xF0) {
#if REPORT_PEN_MAC_ADDR
				pen_mac_addr[0] = point_data[67];
				pen_mac_addr[1] = point_data[68];
				pen_mac_addr[2] = point_data[69];
				pen_mac_addr[3] = point_data[70];
				pen_mac_addr[4] = point_data[71];
				pen_mac_addr[5] = point_data[72];
				//report MAC addr
				if(memcmp(pen_mac_addr,pen_mac_addr_pre,sizeof(pen_mac_addr_pre))){
					kobject_uevent(&nvt_ts_pdev->dev.kobj, KOBJ_CHANGE);
					memcpy(pen_mac_addr_pre,pen_mac_addr,6);
				}
#endif
				goto XFER_ERROR;
			} else if (pen_format_id == 0xF1) {
#if NVT_REPORT_PEN_ID
				ts->penid.results[0] = 0xA5;
				ts->penid.results[1] = 0x5A;

				ts->penid.id[0] = point_data[67];
				ts->penid.id[1] = point_data[68];
				ts->penid.id[2] = point_data[69];
				ts->penid.id[3] = point_data[70];
				ts->penid.id[4] = point_data[71];
				ts->penid.id[5] = point_data[72];
				ts->penid.id[6] = point_data[73];
				ts->penid.checksum = point_data[74];
				ts->penid.type = point_data[75];
#endif
				goto XFER_ERROR;
			} else {
				NVT_ERR("Unknown pen format id!\n");
				goto XFER_ERROR;
			}
		} else { // pen_format_id = 0xFF, i.e. no pen present
#if NVT_DPR_SWITCH
			ts->stylus_event_flag = false;
#endif
			input_report_abs(ts->pen_input_dev, ABS_X, 0);
			input_report_abs(ts->pen_input_dev, ABS_Y, 0);
			input_report_abs(ts->pen_input_dev, ABS_PRESSURE, 0);
			input_report_abs(ts->pen_input_dev, ABS_TILT_X, 0);
			input_report_abs(ts->pen_input_dev, ABS_TILT_Y, 0);
			input_report_abs(ts->pen_input_dev, ABS_DISTANCE, 0);
			input_report_key(ts->pen_input_dev, BTN_TOUCH, 0);
			input_report_key(ts->pen_input_dev, BTN_TOOL_PEN, 0);
			input_report_key(ts->pen_input_dev, BTN_STYLUS, 0);
			input_report_key(ts->pen_input_dev, BTN_STYLUS2, 0);
#if REPORT_PEN_MAC_ADDR
			memset(pen_mac_addr,0,sizeof(pen_mac_addr));
#endif
		}

		input_sync(ts->pen_input_dev);
	} /* if (ts->pen_support) */

XFER_ERROR:

	mutex_unlock(&ts->lock);

#if NVT_CUST_PROC_CMD
	if (wdt_recovery && bTouchIsAwake) {
#if NVT_EDGE_REJECT
		nvt_edge_reject_set(ts->edge_reject_state);
#endif
#if NVT_EDGE_GRID_ZONE
		nvt_edge_grid_zone_set(ts->edge_grid_zone_info.degree,
				       ts->edge_grid_zone_info.direction,
				       ts->edge_grid_zone_info.y1,
				       ts->edge_grid_zone_info.y2);
#endif
#if NVT_PALM_MODE
		nvt_game_mode_set(ts->game_mode_state);
#endif
#if NVT_SUPPORT_PEN
		nvt_support_pen_set(ts->pen_state);
#endif
#ifdef BUILD_LAPIS_TOUCH
        nvt_haptics_set(ts->haptics_state);
#endif
	}
#endif
	return IRQ_HANDLED;
}

/*******************************************************
Description:
	Novatek touchscreen check chip version trim function.

return:
	Executive outcomes. 0---NVT IC. -1---not NVT IC.
*******************************************************/
static int32_t
nvt_ts_check_chip_ver_trim(struct nvt_ts_hw_reg_addr_info hw_regs)
{
	uint8_t buf[8] = { 0 };
	int32_t retry = 0;
	int32_t list = 0;
	int32_t i = 0;
	int32_t found_nvt_chip = 0;
	int32_t ret = -1;
	uint8_t enb_casc = 0;

	/* hw reg mapping */
	ts->chip_ver_trim_addr = hw_regs.chip_ver_trim_addr;
	ts->swrst_sif_addr = hw_regs.swrst_sif_addr;
	ts->crc_err_flag_addr = hw_regs.crc_err_flag_addr;

	NVT_LOG("check chip ver trim with chip_ver_trim_addr=0x%06x, "
		"swrst_sif_addr=0x%06x, crc_err_flag_addr=0x%06x\n",
		ts->chip_ver_trim_addr, ts->swrst_sif_addr,
		ts->crc_err_flag_addr);

	//---Check for 5 times---
	for (retry = 5; retry > 0; retry--) {
		nvt_bootloader_reset();

		nvt_set_page(ts->chip_ver_trim_addr);

		buf[0] = ts->chip_ver_trim_addr & 0x7F;
		buf[1] = 0x00;
		buf[2] = 0x00;
		buf[3] = 0x00;
		buf[4] = 0x00;
		buf[5] = 0x00;
		buf[6] = 0x00;
		CTP_SPI_WRITE(ts->client, buf, 7);

		buf[0] = ts->chip_ver_trim_addr & 0x7F;
		buf[1] = 0x00;
		buf[2] = 0x00;
		buf[3] = 0x00;
		buf[4] = 0x00;
		buf[5] = 0x00;
		buf[6] = 0x00;
		CTP_SPI_READ(ts->client, buf, 7);
		NVT_LOG("buf[1]=0x%02X, buf[2]=0x%02X, buf[3]=0x%02X, buf[4]=0x%02X, buf[5]=0x%02X, buf[6]=0x%02X\n",
			buf[1], buf[2], buf[3], buf[4], buf[5], buf[6]);

		// compare read chip id on supported list
		for (list = 0; list < (sizeof(trim_id_table) /
				       sizeof(struct nvt_ts_trim_id_table));
		     list++) {
			found_nvt_chip = 0;

			// compare each byte
			for (i = 0; i < NVT_ID_BYTE_MAX; i++) {
				if (trim_id_table[list].mask[i]) {
					if (buf[i + 1] !=
					    trim_id_table[list].id[i])
						break;
				}
			}

			if (i == NVT_ID_BYTE_MAX) {
				found_nvt_chip = 1;
			}

			if (found_nvt_chip) {
				NVT_LOG("This is NVT touch IC\n");
				if (trim_id_table[list].mmap->ENB_CASC_REG.addr) {
					/* check single or cascade */
					nvt_read_reg(
						trim_id_table[list]
							.mmap->ENB_CASC_REG,
						&enb_casc);
					/* NVT_LOG("ENB_CASC=0x%02X\n", enb_casc); */
					if (enb_casc & 0x01) {
						NVT_LOG("Single Chip\n");
						ts->mmap =
							trim_id_table[list].mmap;
						ts->is_cascade = false;
					} else {
						NVT_LOG("Cascade Chip\n");
						ts->mmap = trim_id_table[list]
								   .mmap_casc;
						ts->is_cascade = true;
					}
				} else {
					/* for chip that do not have ENB_CASC */
					ts->mmap = trim_id_table[list].mmap;
				}
				ts->hw_crc = trim_id_table[list].hwinfo->hw_crc;
				ts->auto_copy =
					trim_id_table[list].hwinfo->auto_copy;

				/* hw reg re-mapping */
				ts->chip_ver_trim_addr =
					trim_id_table[list]
						.hwinfo->hw_regs
						->chip_ver_trim_addr;
				ts->swrst_sif_addr =
					trim_id_table[list]
						.hwinfo->hw_regs->swrst_sif_addr;
				ts->crc_err_flag_addr =
					trim_id_table[list]
						.hwinfo->hw_regs
						->crc_err_flag_addr;

				NVT_LOG("set reg chip_ver_trim_addr=0x%06x, "
					"swrst_sif_addr=0x%06x, crc_err_flag_addr=0x%06x\n",
					ts->chip_ver_trim_addr,
					ts->swrst_sif_addr,
					ts->crc_err_flag_addr);

				ret = 0;
				goto out;
			} else {
				ts->mmap = NULL;
				ret = -1;
			}
		}

		msleep(10);
	}

out:
	return ret;
}
#if WAKEUP_GESTURE
int nvt_gesture_switch(struct input_dev *dev, unsigned int type, unsigned int code, int value)
{
	NVT_LOG("%s:start\n", __func__);
	if (type == EV_SYN && code == SYN_CONFIG) {
		if (value == WAKEUP_OFF) {
			nvt_gesture_flag = false;
			NVT_LOG("gesture disabled:%d", nvt_gesture_flag);
		} else if (value == WAKEUP_ON) {
			nvt_gesture_flag = true;
			NVT_LOG("gesture enabled:%d", nvt_gesture_flag);
		}
	}
	return 0;
}
#endif
/*******************************************************
Description:
	Novatek touchscreen check chip version trim loop
	function. Check chip version trim via hw regs table.

return:
	Executive outcomes. 0---NVT IC. -1---not NVT IC.
*******************************************************/
static int32_t nvt_ts_check_chip_ver_trim_loop(void)
{
	uint8_t i = 0;
	int32_t ret = 0;

	struct nvt_ts_hw_reg_addr_info hw_regs_table[] = {
		hw_reg_addr_info, hw_reg_addr_info_old_w_isp,
		hw_reg_addr_info_legacy_w_isp
	};

	for (i = 0; i < (sizeof(hw_regs_table) /
			 sizeof(struct nvt_ts_hw_reg_addr_info));
	     i++) {
		//---check chip version trim---
		ret = nvt_ts_check_chip_ver_trim(hw_regs_table[i]);
		if (!ret) {
			break;
		}
	}

	return ret;
}

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY) || IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
static int nvt_ts_check_dt(struct device_node *np)
{
	int i;
	int count;
	struct device_node *node;
	struct drm_panel *panel;

	count = of_count_phandle_with_args(np, "panel", NULL);
	if (count <= 0)
		return 0;

	for (i = 0; i < count; i++) {
		node = of_parse_phandle(np, "panel", i);
		panel = of_drm_find_panel(node);
		of_node_put(node);
		if (!IS_ERR(panel)) {
			active_panel = panel;
			return 0;
		}
	}

	return PTR_ERR(panel);
}
#endif

#if NVT_CUST_PROC_CMD
static void nvt_restore_cmd_func(struct work_struct *work)
{
	NVT_LOG("%s++\n", __func__);
	if (bTouchIsAwake) {
#if NVT_EDGE_REJECT
		nvt_edge_reject_set(ts->edge_reject_state);
#endif
#if NVT_EDGE_GRID_ZONE
		nvt_edge_grid_zone_set(ts->edge_grid_zone_info.degree,
				       ts->edge_grid_zone_info.direction,
				       ts->edge_grid_zone_info.y1,
				       ts->edge_grid_zone_info.y2);
#endif
#if NVT_PALM_MODE
		nvt_game_mode_set(ts->game_mode_state);
#endif
#if NVT_SUPPORT_PEN
		nvt_support_pen_set(ts->pen_state);
#endif
#ifdef BUILD_LAPIS_TOUCH
		nvt_haptics_set(ts->haptics_state);
#endif
#if NVT_DPR_SWITCH
		ts->fw_pen_state= 0;
#endif
	} else {
		NVT_LOG("Touch is already suspend, skip restore cmd\n");
	}
	NVT_LOG("%s--\n", __func__);
}
#endif

int ts_touch_info_uevent(const struct device *dev, struct kobj_uevent_env *env)
{
	int ret = 0;

	ret = add_uevent_var(env, "UEVENT_TO=PEN_FRAMEWORK");
	if(ret)
                return ret;

	ret = add_uevent_var(env, "TYPE=TP");
	if(ret)
		return ret;
#ifdef BUILD_LAPIS_TOUCH
	NVT_LOG("touch_info=%02x", touch_info);
	NVT_LOG("touch_info_pre=%02x",touch_info_pre);
	ret = add_uevent_var(env,"TOUCH_INFORMATION=%02x",touch_info);
	if(ret)
		return ret;
#endif
	ret = add_uevent_var(env,"MAC=%02x:%02x:%02x:%02x:%02x:%02x",
			pen_mac_addr[5],pen_mac_addr[4],
			pen_mac_addr[3],pen_mac_addr[2],
			pen_mac_addr[1],pen_mac_addr[0]);

	if(ret)
		return ret;

	return 0;
}

#if IS_ENABLED(NVT_PLATFORM_DRIVER)
static void nvt_ts_pdev_release(struct device *dev)
{
    kfree(nvt_ts_pdev);
}

static int32_t nvt_ts_platform_device_init(void)
{
	int32_t ret = 0;

	nvt_ts_pdev = kzalloc(sizeof(struct platform_device), GFP_KERNEL);
	if (!nvt_ts_pdev)
		return -ENOMEM;

	nvt_ts_pdev->name = NVT_PLATFORM_DRIVER_NAME;
	nvt_ts_pdev->id = PLATFORM_DEVID_NONE;
	nvt_ts_pdev->num_resources = 0;
	nvt_ts_pdev->dev.platform_data = ts;
	nvt_ts_pdev->dev.release = nvt_ts_pdev_release;

	ret = platform_device_register(nvt_ts_pdev);
	if (ret) {
		NVT_ERR("failed register nvt platform device, %d", ret);
	}

	return ret;
}
#endif

/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 start */
int tp_compare_ic(void)
{
	NVT_LOG("tp_compare_ic in!!");
	/*
	 * TB710FU: no GPIO panel-vendor selector on this board; the touch
	 * firmware ships as a single image (SpendyYT/linux-firmware-tb710fu).
	 * A missing file degrades gracefully - the SPI chip-id reads in
	 * probe still tell us whether the Novatek die is alive.
	 */
	BOOT_UPDATE_FIRMWARE_NAME = "novatek/novatek_nt36532_fw.bin";
	MP_UPDATE_FIRMWARE_NAME = "novatek/novatek_nt36532_mp.bin";
	return 0;
}
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 end */

#if NVT_SET_CHARGER
static void nvt_charger_notify_work(struct work_struct *work)
{
	int ret = 0;
	struct power_supply *psy = NULL;
	union power_supply_propval prop;
	//struct nvt_ts_data *ts = container_of(nb, struct nvt_ts_data, charger_notif);

	if (ts->fw_update_stat != 1)
		return ;

	psy = power_supply_get_by_name("usb");
	if (!psy) {
		NVT_ERR("Couldn't get usbpsy\n");
		return ;
	}

	if (!strcmp(psy->desc->name, "usb")) {
		if (psy && ts) {
			ret = power_supply_get_property(psy, POWER_SUPPLY_PROP_ONLINE, &prop);
			power_supply_put(psy);
			if (ret < 0) {
				NVT_ERR("Couldn't get POWER_SUPPLY_PROP_ONLINE rc=%d\n", ret);
				return ;
			} else {
				if (prop.intval != ts->usb_plug_status) {
					NVT_LOG("usb_plug_status = %d\n", prop.intval);
					ts->usb_plug_status = prop.intval;
					if (!(bTouchIsAwake)){
						if (USB_DETECT_IN == ts->usb_plug_status) {
							tp_charge_flag = true;
							NVT_LOG("USB plug in");
						} else if (USB_DETECT_OUT == ts->usb_plug_status) {
							tp_charge_flag = false;
							NVT_LOG("USB plug out");
						} else {
							NVT_LOG("Charger flag:%d not currently required!\n",ts->usb_plug_status);
						}
						return;
					}
				} else {
					//the same value do nothing.
					return;
				}
			}
		} else {
			power_supply_put(psy);
			return;
		}
	} else {
		power_supply_put(psy);
		return;
	}

	if (NULL == work) {
		NVT_ERR("%s:  parameter work are null!\n", __func__);
		return;
	}

	NVT_LOG("enter nvt_charger_notify_work\n");

	if (USB_DETECT_IN == ts->usb_plug_status) {
		tp_charge_flag = true;
		NVT_LOG("USB plug in");
		if (tp_resume_flag == true)
			nvt_set_charger(USB_DETECT_IN);
	} else if (USB_DETECT_OUT == ts->usb_plug_status) {
		tp_charge_flag = false;
		NVT_LOG("USB plug out");
		if (tp_resume_flag == true)
			nvt_set_charger(USB_DETECT_OUT);
	} else {
		NVT_LOG("Charger flag:%d not currently required!\n",ts->usb_plug_status);
	}

}

static int nvt_charger_notifier_callback(struct notifier_block *nb,unsigned long val, void *v)
{

	if(ts->nvt_charger_notify_wq != NULL && val == POWER_SUPPLY_PROP_STATUS)
		queue_work(ts->nvt_charger_notify_wq, &ts->charger_notify_work);

	return 0;
}

void nvt_charger_init(void)
{
	int ret = 0;
	struct power_supply *psy = NULL;
	union power_supply_propval prop;

	ts->nvt_charger_notify_wq = create_singlethread_workqueue("nvt_charger_wq");
	if (!ts->nvt_charger_notify_wq) {
		NVT_ERR("allocate nvt_charger_notify_wq failed\n");
		return;
	}
	INIT_WORK(&ts->charger_notify_work, nvt_charger_notify_work);
	ts->charger_notif.notifier_call = nvt_charger_notifier_callback;
	ret = power_supply_reg_notifier(&ts->charger_notif);
	if (ret) {
		NVT_ERR("Unable to register charger_notifier: %d\n",ret);
	}

	/* if power supply supplier registered brfore TP
	* ps_notify_callback will not receive PSY_EVENT_PROP_ADDED
	* event, and will cause miss to set TP into charger state.
	* So check PS state in probe.
	*/
	psy = power_supply_get_by_name("usb");
	if (psy) {
		ret = power_supply_get_property(psy, POWER_SUPPLY_PROP_ONLINE, &prop);
		if (ret < 0) {
			NVT_ERR("Couldn't get POWER_SUPPLY_PROP_ONLINE rc=%d\n", ret);
		} else {
			ts->usb_plug_status = prop.intval;
			NVT_LOG("boot check usb_plug_status = %d\n", prop.intval);
		}
	}
}
#endif

static void nvt_pen_input_config(void)
{
	//---set pen input device info.---
	ts->pen_input_dev->evbit[0] =
		BIT_MASK(EV_SYN) | BIT_MASK(EV_KEY) | BIT_MASK(EV_ABS);
	ts->pen_input_dev->keybit[BIT_WORD(BTN_TOUCH)] =
		BIT_MASK(BTN_TOUCH);
	ts->pen_input_dev->keybit[BIT_WORD(BTN_TOOL_PEN)] |=
		BIT_MASK(BTN_TOOL_PEN);
	//ts->pen_input_dev->keybit[BIT_WORD(BTN_TOOL_RUBBER)] |= BIT_MASK(BTN_TOOL_RUBBER);
	ts->pen_input_dev->keybit[BIT_WORD(BTN_STYLUS)] |=
		BIT_MASK(BTN_STYLUS);
	ts->pen_input_dev->keybit[BIT_WORD(BTN_STYLUS2)] |=
		BIT_MASK(BTN_STYLUS2);
	ts->pen_input_dev->propbit[0] = BIT(INPUT_PROP_DIRECT);

	input_set_abs_params(ts->pen_input_dev, ABS_X, 0, PEN_MAX_WIDTH,
			     0, 0);
	input_set_abs_params(ts->pen_input_dev, ABS_Y, 0,
			     PEN_MAX_HEIGHT, 0, 0);
	input_set_abs_params(ts->pen_input_dev, ABS_PRESSURE, 0,
			     PEN_PRESSURE_MAX, 0, 0);
	input_set_abs_params(ts->pen_input_dev, ABS_DISTANCE, 0,
			     PEN_DISTANCE_MAX, 0, 0);
	input_set_abs_params(ts->pen_input_dev, ABS_TILT_X,
			     PEN_TILT_MIN, PEN_TILT_MAX, 0, 0);
	input_set_abs_params(ts->pen_input_dev, ABS_TILT_Y,
			     PEN_TILT_MIN, PEN_TILT_MAX, 0, 0);

	sprintf(ts->pen_phys, "input/pen");
	ts->pen_input_dev->name = NVT_PEN_NAME;
	ts->pen_input_dev->phys = ts->pen_phys;
	ts->pen_input_dev->id.bustype = BUS_SPI;
}


void nvt_pen_max_pressure_reconfig(uint8_t level)
{
	int ret = 0;
	int max_pressure = PEN_PRESSURE_MAX;

	if (level == 1) {
		max_pressure = 8191;
	}

	// pen input need reconfig

	if (ts->pen_input_dev != NULL) {
		input_unregister_device(ts->pen_input_dev);
		input_free_device(ts->pen_input_dev);
		ts->pen_input_dev = NULL;
	}

	//---allocate pen input device---
	ts->pen_input_dev = input_allocate_device();
	if (ts->pen_input_dev == NULL) {
		NVT_ERR("reconfig allocate pen input device failed\n");
		ret = -ENOMEM;
	}

	if (ts->pen_input_dev != NULL){
		nvt_pen_input_config();
	}
	//change pen max pressure
	input_set_abs_params(ts->pen_input_dev, ABS_PRESSURE, 0, max_pressure, 0, 0);

	ret = input_register_device(ts->pen_input_dev);
	if (ret) {
		NVT_ERR("register pen input device (%s) failed. ret=%d\n",
			ts->pen_input_dev->name, ret);
	}
}

/*******************************************************
Description:
	Novatek touchscreen driver probe function.

return:
	Executive outcomes. 0---succeed. negative---failed
*******************************************************/
/* Kirby code for KIRBYU-3835  at 2024/7/25 start */
bool dsi_panel_enable_flag = false;
EXPORT_SYMBOL(dsi_panel_enable_flag);
bool nvt_ts_probe_flag = true;
EXPORT_SYMBOL(nvt_ts_probe_flag);
/* Kirby code for KIRBYU-3835  at 2024/7/25 end*/

static int32_t nvt_ts_probe(struct spi_device *client)
{
	int32_t ret = 0;
#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY) || IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	struct device_node *dp = NULL;
#endif
#if IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	void *cookie = NULL;
#endif
#if ((TOUCH_KEY_NUM > 0) || WAKEUP_GESTURE)
	int32_t retry = 0;
#endif
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 start */
#if BOOT_UPDATE_FIRMWARE
	tp_compare_ic();
	NVT_LOG("tp_compare_ic_in_probe");
#endif
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 end */
#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY) || IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	dp = client->dev.of_node;

	ret = nvt_ts_check_dt(dp);
	if (ret == -EPROBE_DEFER) {
		return ret;
	}

	if (ret) {
		ret = -ENODEV;
		return ret;
	}
#endif

#ifdef BUILD_KIRBY_TOUCH
	NVT_LOG("nt36523n probe start\n");
#else
	NVT_LOG("nt36532 probe start\n");
#endif
	ts = (struct nvt_ts_data *)kzalloc(sizeof(struct nvt_ts_data),
					   GFP_KERNEL);
	if (ts == NULL) {
		NVT_ERR("failed to allocated memory for nvt ts data\n");
		return -ENOMEM;
	}

	ts->xbuf = (uint8_t *)kzalloc(NVT_XBUF_LEN, GFP_KERNEL);
	if (ts->xbuf == NULL) {
		NVT_ERR("kzalloc for xbuf failed!\n");
		ret = -ENOMEM;
		goto err_malloc_xbuf;
	}

	ts->rbuf = (uint8_t *)kzalloc(NVT_READ_LEN, GFP_KERNEL);
	if (ts->rbuf == NULL) {
		NVT_ERR("kzalloc for rbuf failed!\n");
		ret = -ENOMEM;
		goto err_malloc_rbuf;
	}

#if NVT_PM_WAIT_BUS_RESUME_COMPLETE
	ts->dev_pm_suspend = false;
	init_completion(&ts->dev_pm_resume_completion);
#endif /* NVT_PM_WAIT_BUS_RESUME_COMPLETE */

	ts->client = client;
	spi_set_drvdata(client, ts);

	//---prepare for spi parameter---
	if (ts->client->controller->flags & SPI_CONTROLLER_HALF_DUPLEX) {
		NVT_ERR("Full duplex not supported by master\n");
		ret = -EIO;
		goto err_ckeck_full_duplex;
	}
	ts->client->bits_per_word = 8;
	ts->client->mode = SPI_MODE_0;

	ret = spi_setup(ts->client);
	if (ret < 0) {
		NVT_ERR("Failed to perform SPI setup\n");
		goto err_spi_setup;
	}

#ifdef CONFIG_MTK_SPI
	/* old usage of MTK spi API */
	memcpy(&ts->spi_ctrl, &spi_ctrdata, sizeof(struct mt_chip_conf));
	ts->client->controller_data = (void *)&ts->spi_ctrl;
#endif

#if 0 /* TB710FU: MediaTek SPI platform */
	/* new usage of MTK spi API */
	memcpy(&ts->spi_ctrl, &spi_ctrdata, sizeof(struct mtk_chip_config));
	ts->client->controller_data = (void *)&ts->spi_ctrl;
#endif

	NVT_LOG("mode=%d, max_speed_hz=%d\n", ts->client->mode,
		ts->client->max_speed_hz);

	//---parse dts---
	ret = nvt_parse_dt(&client->dev);
	if (ret) {
		NVT_ERR("parse dt error\n");
		goto err_spi_setup;
	}

	//---request and config GPIOs---
	ret = nvt_gpio_config(ts);
	if (ret) {
		NVT_ERR("gpio config error!\n");
		goto err_gpio_config_failed;
	}

	mutex_init(&ts->lock);
	mutex_init(&ts->xbuf_lock);

	//---eng reset before TP_RESX high
	nvt_eng_reset();

#if NVT_TOUCH_SUPPORT_HW_RST
	gpiod_set_value(ts->reset_desc, 1);
#endif

	// need 10ms delay after POR(power on reset)
	msleep(10);

	//---check chip version trim---
	ret = nvt_ts_check_chip_ver_trim_loop();
	if (ret) {
		NVT_ERR("chip is not identified\n");
		ret = -EINVAL;
		goto err_chipvertrim_failed;
	}

	//---allocate input device---
	ts->input_dev = input_allocate_device();
	if (ts->input_dev == NULL) {
		NVT_ERR("allocate input device failed\n");
		ret = -ENOMEM;
		goto err_input_dev_alloc_failed;
	}

	ts->max_touch_num = TOUCH_MAX_FINGER_NUM;

#if TOUCH_KEY_NUM > 0
	ts->max_button_num = TOUCH_KEY_NUM;
#endif

	ts->int_trigger_type = nvt_int_trigger;

	//---set input device info.---
	ts->input_dev->evbit[0] = BIT_MASK(EV_SYN) | BIT_MASK(EV_KEY) |
				  BIT_MASK(EV_ABS);
	ts->input_dev->keybit[BIT_WORD(BTN_TOUCH)] = BIT_MASK(BTN_TOUCH);
	ts->input_dev->propbit[0] = BIT(INPUT_PROP_DIRECT);

#if MT_PROTOCOL_B
	input_mt_init_slots(ts->input_dev, ts->max_touch_num, 0);
#endif

	input_set_abs_params(ts->input_dev, ABS_MT_PRESSURE, 0, TOUCH_FORCE_NUM,
			     0, 0); //pressure = TOUCH_FORCE_NUM

#if TOUCH_MAX_FINGER_NUM > 1
	input_set_abs_params(ts->input_dev, ABS_MT_TOUCH_MAJOR, 0, 255, 0,
			     0); //area = 255

	input_set_abs_params(ts->input_dev, ABS_MT_POSITION_X, 0,
			     TOUCH_MAX_WIDTH, 0, 0);
	input_set_abs_params(ts->input_dev, ABS_MT_POSITION_Y, 0,
			     TOUCH_MAX_HEIGHT, 0, 0);
#if MT_PROTOCOL_B
	// no need to set ABS_MT_TRACKING_ID, input_mt_init_slots() already set it
#else
	input_set_abs_params(ts->input_dev, ABS_MT_TRACKING_ID, 0,
			     ts->max_touch_num, 0, 0);
#endif //MT_PROTOCOL_B
#endif //TOUCH_MAX_FINGER_NUM > 1

#if TOUCH_KEY_NUM > 0
	for (retry = 0; retry < ts->max_button_num; retry++) {
		input_set_capability(ts->input_dev, EV_KEY,
				     touch_key_array[retry]);
	}
#endif

#if NVT_DPR_SWITCH
	input_set_capability(ts->input_dev, EV_KEY, KEY_SKIN_STYLUS);
#endif
#if WAKEUP_GESTURE
	for (retry = 0;
	     retry < (sizeof(gesture_key_array) / sizeof(gesture_key_array[0]));
	     retry++) {
		input_set_capability(ts->input_dev, EV_KEY,
				     gesture_key_array[retry]);
	}
	ts->input_dev->event = nvt_gesture_switch;
	input_set_capability(ts->input_dev, EV_KEY, 523);
#endif
	sprintf(ts->phys, "input/ts");
	ts->input_dev->name = NVT_TS_NAME;
	ts->input_dev->phys = ts->phys;
	ts->input_dev->id.bustype = BUS_SPI;

	//---register input device---
	ret = input_register_device(ts->input_dev);
	if (ret) {
		NVT_ERR("register input device (%s) failed. ret=%d\n",
			ts->input_dev->name, ret);
		goto err_input_register_device_failed;
	}

	if (ts->pen_support) {
		//---allocate pen input device---
		ts->pen_input_dev = input_allocate_device();
		if (ts->pen_input_dev == NULL) {
			NVT_ERR("allocate pen input device failed\n");
			ret = -ENOMEM;
			goto err_pen_input_dev_alloc_failed;
		}
		nvt_pen_input_config();
		//---register pen input device---
		ret = input_register_device(ts->pen_input_dev);
		if (ret) {
			NVT_ERR("register pen input device (%s) failed. ret=%d\n",
				ts->pen_input_dev->name, ret);
			goto err_pen_input_register_device_failed;
		}
	} /* if (ts->pen_support) */

	//---set int-pin & request irq---
	if (client->irq <= 0)
		client->irq = nvt_irq_from_dt(&client->dev);
	NVT_LOG("irq=%d int_trigger_type=%d\n", client->irq,
			ts->int_trigger_type);
	if (client->irq > 0) {
		NVT_LOG("int_trigger_type=%d\n", ts->int_trigger_type);
		ts->irq_enabled = true;
		ret = request_threaded_irq(client->irq, NULL, nvt_ts_work_func,
					   ts->int_trigger_type | IRQF_ONESHOT,
					   NVT_SPI_NAME, ts);
		if (ret != 0) {
			NVT_ERR("request irq failed. ret=%d\n", ret);
			goto err_int_request_failed;
		} else {
			nvt_irq_enable(false);
			NVT_LOG("request irq %d succeed\n", client->irq);
		}
	} else {
		/* Without an irq the driver still identifies the die and can
		 * read it over SPI, but it never reports a touch. */
		NVT_ERR("no usable irq (ret=%d) - continuing without it\n",
				client->irq);
		client->irq = 0;
	}

#if WAKEUP_GESTURE
	device_init_wakeup(&ts->client->dev, 1);
#endif
#if NVT_SET_CHARGER
	nvt_charger_init();
#endif
#if BOOT_UPDATE_FIRMWARE
	nvt_fwu_wq =
		alloc_workqueue("nvt_fwu_wq", WQ_UNBOUND | WQ_MEM_RECLAIM, 1);
	if (!nvt_fwu_wq) {
		NVT_ERR("nvt_fwu_wq create workqueue failed\n");
		ret = -ENOMEM;
		goto err_create_nvt_fwu_wq_failed;
	}
	INIT_DELAYED_WORK(&ts->nvt_fwu_work, Boot_Update_Firmware);

	// please make sure boot update start after display reset(RESX) sequence
/* Kirby code for KIRBYU-3835  at 2024/7/25 start */
	//load fw in probe during startup.After the system start,the fw is loaded when the lcd on
	if (nvt_ts_probe_flag == true){
	queue_delayed_work(nvt_fwu_wq, &ts->nvt_fwu_work,
			   msecs_to_jiffies(5000));
	NVT_LOG("nvt_ts_probe_flag is true\n");
	dsi_panel_enable_flag = true;
	}
/* Kirby code for KIRBYU-3835  at 2024/7/25 end*/

#endif

	NVT_LOG("NVT_TOUCH_ESD_PROTECT is %d\n", NVT_TOUCH_ESD_PROTECT);
#if NVT_TOUCH_ESD_PROTECT
	INIT_DELAYED_WORK(&nvt_esd_check_work, nvt_esd_check_func);
	nvt_esd_check_wq =
		alloc_workqueue("nvt_esd_check_wq", WQ_MEM_RECLAIM, 1);
	if (!nvt_esd_check_wq) {
		NVT_ERR("nvt_esd_check_wq create workqueue failed\n");
		ret = -ENOMEM;
		goto err_create_nvt_esd_check_wq_failed;
	}
	queue_delayed_work(nvt_esd_check_wq, &nvt_esd_check_work,
			   msecs_to_jiffies(NVT_TOUCH_ESD_CHECK_PERIOD));
#endif /* #if NVT_TOUCH_ESD_PROTECT */

#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
       INIT_DELAYED_WORK(&nvt_hall_check_work, nvt_hall_check_func);
       nvt_hall_check_wq = create_workqueue("nvt_hall_check_wq");
       if (!nvt_hall_check_wq) {
               NVT_ERR("nvt_hall_check_wqsd_check_wq create workqueue failed\n");
               ret = -ENOMEM;
               goto err_create_nvt_hall_check_wq_failed;
       }
#endif
#endif

	//---set device node---
#if NVT_TOUCH_PROC
	ret = nvt_flash_proc_init();
	if (ret != 0) {
		NVT_ERR("nvt flash proc init failed. ret=%d\n", ret);
		goto err_flash_proc_init_failed;
	}
#endif

#if NVT_TOUCH_EXT_PROC
	ret = nvt_extra_proc_init();
	if (ret != 0) {
		NVT_ERR("nvt extra proc init failed. ret=%d\n", ret);
		goto err_extra_proc_init_failed;
	}
#endif

#if NVT_TOUCH_MP
	ret = nvt_mp_proc_init();
	if (ret != 0) {
		NVT_ERR("nvt mp proc init failed. ret=%d\n", ret);
		goto err_mp_proc_init_failed;
	}
#endif

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
	ts->drm_panel_notif.notifier_call = nvt_drm_panel_notifier_callback;
	if (active_panel) {
		ret = drm_panel_notifier_register(active_panel,
						  &ts->drm_panel_notif);
		if (ret < 0) {
			NVT_ERR("register drm_panel_notifier failed. ret=%d\n",
				ret);
			goto err_register_suspend_resume_failed;
		}
	}
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
	ts->drm_notif.notifier_call = nvt_drm_notifier_callback;
	ret = msm_drm_register_client(&ts->drm_notif);
	if (ret) {
		NVT_ERR("register drm_notifier failed. ret=%d\n", ret);
		goto err_register_suspend_resume_failed;
	}
#elif IS_ENABLED(NVT_FB_NOTIFY)
	ts->fb_notif.notifier_call = nvt_fb_notifier_callback;
	ret = fb_register_client(&ts->fb_notif);
	if (ret) {
		NVT_ERR("register fb_notifier failed. ret=%d\n", ret);
		goto err_register_suspend_resume_failed;
	}
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
	ts->early_suspend.level = EARLY_SUSPEND_LEVEL_BLANK_SCREEN + 1;
	ts->early_suspend.suspend = nvt_ts_early_suspend;
	ts->early_suspend.resume = nvt_ts_late_resume;
	ret = register_early_suspend(&ts->early_suspend);
	if (ret) {
		NVT_ERR("register early suspend failed. ret=%d\n", ret);
		goto err_register_suspend_resume_failed;
	}
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	if (active_panel) {
		cookie = panel_event_notifier_register(
			PANEL_EVENT_NOTIFICATION_PRIMARY,
			PANEL_EVENT_NOTIFIER_CLIENT_PRIMARY_TOUCH, active_panel,
			&nvt_panel_notifier_callback, ts);
	}

	if (!cookie) {
		NVT_ERR("register qcom panel_event_notifier failed\n");
		goto err_register_suspend_resume_failed;
	}

	notifier_cookie = cookie;
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
	ts->disp_notifier.notifier_call = nvt_mtk_drm_notifier_callback;
	ret = mtk_disp_notifier_register(NVT_SPI_NAME, &ts->disp_notifier);
	if (ret) {
		NVT_ERR("register mtk_disp_notifier failed\n");
		goto err_register_suspend_resume_failed;
	}
#endif

	bTouchIsAwake = 1;

#if NVT_CUST_PROC_CMD
	ts->edge_reject_state = 0;
	ts->game_mode_state = 0;
	ts->pen_state = 0;
#if NVT_DPR_SWITCH
	ts->fw_pen_state = 0;
#endif
#ifdef BUILD_LAPIS_TOUCH
	ts->haptics_state = 0;
#endif
	INIT_WORK(&ts_restore_cmd_work, nvt_restore_cmd_func);
	ts->probe_state = 1;
#if NVT_DPR_SWITCH
	ts->finger_event_flag = false;
	ts->stylus_event_flag = false;
#endif
#endif
#ifdef BUILD_KIRBY_TOUCH
	NVT_LOG("nt36523n probe end\n");
#else
	NVT_LOG("nt36532 probe end\n");
#endif
#if IS_ENABLED(NVT_PLATFORM_DRIVER)
	/* ts platform deivce */
	ret = nvt_ts_platform_device_init();
	if (ret) {
		NVT_ERR("nvt_ts_platform_device_init failed\n");
		goto err_platform_device_init_failed;
	}

	ret = nvt_ts_platform_driver_init();
	if (ret) {
		NVT_ERR("nvt_ts_platform_driver_init failed\n");
		goto err_platform_driver_init_failed;
	}
#endif

	NVT_LOG("end\n");
	nvt_irq_enable(true);
	schedule_delayed_work(&nvt_fw_health_dwork, msecs_to_jiffies(10000));

	return 0;

#if IS_ENABLED(NVT_PLATFORM_DRIVER)
err_platform_driver_init_failed:
	platform_device_unregister(nvt_ts_pdev);
err_platform_device_init_failed:
	kfree(nvt_ts_pdev);
	nvt_ts_pdev = NULL;
#endif

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
	if (active_panel) {
		if (drm_panel_notifier_unregister(active_panel,
						  &ts->drm_panel_notif))
			NVT_ERR("Error occurred while unregistering drm_panel_notifier.\n");
	}
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
	if (msm_drm_unregister_client(&ts->drm_notif))
		NVT_ERR("Error occurred while unregistering drm_notifier.\n");
#elif IS_ENABLED(NVT_FB_NOTIFY)
	if (fb_unregister_client(&ts->fb_notif))
		NVT_ERR("Error occurred while unregistering fb_notifier.\n");
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
	unregister_early_suspend(&ts->early_suspend);
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	if (active_panel && notifier_cookie)
		panel_event_notifier_unregister(notifier_cookie);
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
	mtk_disp_notifier_unregister(&ts->disp_notifier);
#endif

err_register_suspend_resume_failed:
#if NVT_TOUCH_MP
	nvt_mp_proc_deinit();
err_mp_proc_init_failed:
#endif
#if NVT_TOUCH_EXT_PROC
	nvt_extra_proc_deinit();
err_extra_proc_init_failed:
#endif
#if NVT_TOUCH_PROC
	nvt_flash_proc_deinit();
err_flash_proc_init_failed:
#endif

#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
if (nvt_hall_check_wq) {
               cancel_delayed_work_sync(&nvt_hall_check_work);
               destroy_workqueue(nvt_hall_check_wq);
               nvt_hall_check_wq = NULL;
       }
err_create_nvt_hall_check_wq_failed:
#endif
#endif

#if NVT_TOUCH_ESD_PROTECT
	if (nvt_esd_check_wq) {
		cancel_delayed_work_sync(&nvt_esd_check_work);
		destroy_workqueue(nvt_esd_check_wq);
		nvt_esd_check_wq = NULL;
	}
err_create_nvt_esd_check_wq_failed:
#endif
#if BOOT_UPDATE_FIRMWARE
	if (nvt_fwu_wq) {
		cancel_delayed_work_sync(&ts->nvt_fwu_work);
		destroy_workqueue(nvt_fwu_wq);
		nvt_fwu_wq = NULL;
	}
err_create_nvt_fwu_wq_failed:
#endif
#if NVT_SET_CHARGER
	if (ts->nvt_charger_notify_wq) {
		cancel_work_sync(&ts->charger_notify_work);
		destroy_workqueue(ts->nvt_charger_notify_wq);
		ts->nvt_charger_notify_wq = NULL;
	}
	power_supply_unreg_notifier(&ts->charger_notif);
#endif
#if WAKEUP_GESTURE
	device_init_wakeup(&ts->client->dev, 0);
#endif
	free_irq(client->irq, ts);
err_int_request_failed:
	if (ts->pen_support) {
		input_unregister_device(ts->pen_input_dev);
		ts->pen_input_dev = NULL;
	}
err_pen_input_register_device_failed:
	if (ts->pen_support) {
		if (ts->pen_input_dev) {
			input_free_device(ts->pen_input_dev);
			ts->pen_input_dev = NULL;
		}
	}
err_pen_input_dev_alloc_failed:
	input_unregister_device(ts->input_dev);
	ts->input_dev = NULL;
err_input_register_device_failed:
	if (ts->input_dev) {
		input_free_device(ts->input_dev);
		ts->input_dev = NULL;
	}
err_input_dev_alloc_failed:
err_chipvertrim_failed:
	mutex_destroy(&ts->xbuf_lock);
	mutex_destroy(&ts->lock);
	nvt_gpio_deconfig(ts);
err_gpio_config_failed:
err_spi_setup:
err_ckeck_full_duplex:
	spi_set_drvdata(client, NULL);
	if (ts->rbuf) {
		kfree(ts->rbuf);
		ts->rbuf = NULL;
	}
err_malloc_rbuf:
	if (ts->xbuf) {
		kfree(ts->xbuf);
		ts->xbuf = NULL;
	}
err_malloc_xbuf:
	if (ts) {
		kfree(ts);
		ts = NULL;
	}
	return ret;
}

/*******************************************************
Description:
	Novatek touchscreen driver release function.

return:
	Executive outcomes. 0---succeed.
*******************************************************/
static void nvt_ts_remove(struct spi_device *client)
{
	NVT_LOG("Removing driver...\n");

#if IS_ENABLED(NVT_PLATFORM_DRIVER)
	platform_device_unregister(nvt_ts_pdev);
#endif

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
	if (active_panel) {
		if (drm_panel_notifier_unregister(active_panel,
						  &ts->drm_panel_notif))
			NVT_ERR("Error occurred while unregistering drm_panel_notifier.\n");
	}
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
	if (msm_drm_unregister_client(&ts->drm_notif))
		NVT_ERR("Error occurred while unregistering drm_notifier.\n");
#elif IS_ENABLED(NVT_FB_NOTIFY)
	if (fb_unregister_client(&ts->fb_notif))
		NVT_ERR("Error occurred while unregistering fb_notifier.\n");
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
	unregister_early_suspend(&ts->early_suspend);
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	if (active_panel && notifier_cookie)
		panel_event_notifier_unregister(notifier_cookie);
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
	mtk_disp_notifier_unregister(&ts->disp_notifier);
#endif
#if NVT_SET_CHARGER
	power_supply_unreg_notifier(&ts->charger_notif);
#endif
#if NVT_TOUCH_MP
	nvt_mp_proc_deinit();
#endif
#if NVT_TOUCH_EXT_PROC
	nvt_extra_proc_deinit();
#endif
#if NVT_TOUCH_PROC
	nvt_flash_proc_deinit();
#endif

#if NVT_TOUCH_ESD_PROTECT
	if (nvt_esd_check_wq) {
		cancel_delayed_work_sync(&nvt_esd_check_work);
		nvt_esd_check_enable(false);
		destroy_workqueue(nvt_esd_check_wq);
		nvt_esd_check_wq = NULL;
	}
#endif

#if BOOT_UPDATE_FIRMWARE
	if (nvt_fwu_wq) {
		cancel_delayed_work_sync(&ts->nvt_fwu_work);
		destroy_workqueue(nvt_fwu_wq);
		nvt_fwu_wq = NULL;
	}
#endif

#if WAKEUP_GESTURE
	device_init_wakeup(&ts->client->dev, 0);
#endif

	cancel_delayed_work_sync(&nvt_fw_health_dwork);

#if IS_ENABLED(NVT_PLATFORM_DRIVER)
	platform_device_unregister(nvt_ts_pdev);
#endif

	nvt_irq_enable(false);
	free_irq(client->irq, ts);

	mutex_destroy(&ts->xbuf_lock);
	mutex_destroy(&ts->lock);

	nvt_gpio_deconfig(ts);

	if (ts->pen_support) {
		if (ts->pen_input_dev) {
			input_unregister_device(ts->pen_input_dev);
			ts->pen_input_dev = NULL;
		}
	}

	if (ts->input_dev) {
		input_unregister_device(ts->input_dev);
		ts->input_dev = NULL;
	}

	spi_set_drvdata(client, NULL);

	if (ts->xbuf) {
		kfree(ts->xbuf);
		ts->xbuf = NULL;
	}

	if (ts) {
		kfree(ts);
		ts = NULL;
	}
}

static void nvt_ts_shutdown(struct spi_device *client)
{
	NVT_LOG("Shutdown driver...\n");

	nvt_irq_enable(false);

#if IS_ENABLED(NVT_PLATFORM_DRIVER)
	platform_device_unregister(nvt_ts_pdev);
#endif

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
	if (active_panel) {
		if (drm_panel_notifier_unregister(active_panel,
						  &ts->drm_panel_notif))
			NVT_ERR("Error occurred while unregistering drm_panel_notifier.\n");
	}
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
	if (msm_drm_unregister_client(&ts->drm_notif))
		NVT_ERR("Error occurred while unregistering drm_notifier.\n");
#elif IS_ENABLED(NVT_FB_NOTIFY)
	if (fb_unregister_client(&ts->fb_notif))
		NVT_ERR("Error occurred while unregistering fb_notifier.\n");
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
	unregister_early_suspend(&ts->early_suspend);
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
	if (active_panel && notifier_cookie)
		panel_event_notifier_unregister(notifier_cookie);
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
	mtk_disp_notifier_unregister(&ts->disp_notifier);
#endif

#if NVT_TOUCH_MP
	nvt_mp_proc_deinit();
#endif
#if NVT_TOUCH_EXT_PROC
	nvt_extra_proc_deinit();
#endif
#if NVT_TOUCH_PROC
	nvt_flash_proc_deinit();
#endif

#if NVT_TOUCH_ESD_PROTECT
	if (nvt_esd_check_wq) {
		cancel_delayed_work_sync(&nvt_esd_check_work);
		nvt_esd_check_enable(false);
		destroy_workqueue(nvt_esd_check_wq);
		nvt_esd_check_wq = NULL;
	}
#endif /* #if NVT_TOUCH_ESD_PROTECT */

#if BOOT_UPDATE_FIRMWARE
	if (nvt_fwu_wq) {
		cancel_delayed_work_sync(&ts->nvt_fwu_work);
		destroy_workqueue(nvt_fwu_wq);
		nvt_fwu_wq = NULL;
	}
#endif

#if WAKEUP_GESTURE
	device_init_wakeup(&ts->client->dev, 0);
#endif
}

/*******************************************************
Description:
	Novatek touchscreen driver suspend function.

return:
	Executive outcomes. 0---succeed.
*******************************************************/
static int32_t nvt_ts_suspend(struct device *dev)
{
#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
	int hall_work_status = -1;
#endif
#endif
	uint8_t buf[4] = { 0 };
#if MT_PROTOCOL_B
	uint32_t i = 0;
#endif

	tp_resume_flag = false;
#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
	hall_work_status = gpio_get_value(501);
#endif
#endif
	if (!bTouchIsAwake) {
		NVT_LOG("Touch is already suspend\n");
		return 0;
	}

#if WAKEUP_GESTURE
	if (nvt_gesture_flag == false)
		nvt_irq_enable(false);
#else
	nvt_irq_enable(false);
#endif

#if NVT_TOUCH_ESD_PROTECT
	NVT_LOG("cancel delayed work sync\n");
	cancel_delayed_work_sync(&nvt_esd_check_work);
	nvt_esd_check_enable(false);
#endif /* #if NVT_TOUCH_ESD_PROTECT */

	mutex_lock(&ts->lock);

	NVT_LOG("start\n");

	bTouchIsAwake = 0;

#if WAKEUP_GESTURE
	//---write command to enter "wakeup gesture mode"---
#ifdef BUILD_LAPIS_TOUCH
  #if NVT_HALL_CHECK
	if ((nvt_gesture_flag == true) && !(hall_work_status == 0)) {
  #else
        if (nvt_gesture_flag == true) {
  #endif
#else
	if (nvt_gesture_flag == true) {
#endif
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = 0x13;
		CTP_SPI_WRITE(ts->client, buf, 2);
		enable_irq_wake(ts->client->irq);
		NVT_LOG("Enabled touch wakeup gesture\n");
#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
		nvt_hall_pm = 0;
		nvt_hall_pm_status = 0;
		queue_delayed_work(nvt_hall_check_wq, &nvt_hall_check_work,
			msecs_to_jiffies(NVT_HALL_WORK_DELAY));
		NVT_LOG("Enabled nvt_hall_check_work\n");
#endif
#endif
	} else {
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = 0x11;
		CTP_SPI_WRITE(ts->client, buf, 2);
	}

#else // WAKEUP_GESTURE \
	//---write command to enter "deep sleep mode"---
	buf[0] = EVENT_MAP_HOST_CMD;
	buf[1] = 0x11;
	CTP_SPI_WRITE(ts->client, buf, 2);
#endif // WAKEUP_GESTURE

	msleep(50);

	mutex_unlock(&ts->lock);

	/* release all touches */
#if MT_PROTOCOL_B
	for (i = 0; i < ts->max_touch_num; i++) {
		input_mt_slot(ts->input_dev, i);
		input_report_abs(ts->input_dev, ABS_MT_TOUCH_MAJOR, 0);
		input_report_abs(ts->input_dev, ABS_MT_PRESSURE, 0);
		input_mt_report_slot_state(ts->input_dev, MT_TOOL_FINGER, 0);
	}
#endif
	input_report_key(ts->input_dev, BTN_TOUCH, 0);
#if !MT_PROTOCOL_B
	input_mt_sync(ts->input_dev);
#endif
	input_sync(ts->input_dev);

	/* release pen event */
	if (ts->pen_support) {
		input_report_abs(ts->pen_input_dev, ABS_X, 0);
		input_report_abs(ts->pen_input_dev, ABS_Y, 0);
		input_report_abs(ts->pen_input_dev, ABS_PRESSURE, 0);
		input_report_abs(ts->pen_input_dev, ABS_TILT_X, 0);
		input_report_abs(ts->pen_input_dev, ABS_TILT_Y, 0);
		input_report_abs(ts->pen_input_dev, ABS_DISTANCE, 0);
		input_report_key(ts->pen_input_dev, BTN_TOUCH, 0);
		input_report_key(ts->pen_input_dev, BTN_TOOL_PEN, 0);
		input_report_key(ts->pen_input_dev, BTN_STYLUS, 0);
		input_report_key(ts->pen_input_dev, BTN_STYLUS2, 0);
		input_sync(ts->pen_input_dev);
	}

	NVT_LOG("end\n");

	return 0;
}
/* Kirby code for KIRBYU-3835  at 2024/7/25 start */
void nvt_nvt_update_firmware_work(struct completion *load_fw_completion)
{
	NVT_LOG("nvt_update_firmware,start\n");
	ts->load_fw_completion = load_fw_completion;
	queue_delayed_work(nvt_fwu_wq, &ts->nvt_fwu_work, msecs_to_jiffies(0));
	NVT_LOG("nvt_update_firmware,end\n");
}
EXPORT_SYMBOL(nvt_nvt_update_firmware_work);
/* Kirby code for KIRBYU-3835  at 2024/7/25 end */


/*******************************************************
Description:
	Novatek touchscreen driver resume function.

return:
	Executive outcomes. 0---succeed.
*******************************************************/
static int32_t nvt_ts_resume(struct device *dev)
{
	int32_t ret = 0;
	uint8_t buf[4] = { 0 };
	tp_resume_flag = true;
#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
	if(nvt_gesture_flag == true){
		cancel_delayed_work_sync(&nvt_hall_check_work);
	}
	NVT_LOG("Disable nvt_hall_check_work\n");
#endif
#endif
	if (bTouchIsAwake) {
		NVT_LOG("Touch is already resume\n");
		return 0;
	}

	mutex_lock(&ts->lock);

	NVT_LOG("start\n");

	// please make sure display reset(RESX) sequence and mipi dsi cmds sent before this
#if NVT_TOUCH_SUPPORT_HW_RST
	gpiod_set_value(ts->reset_desc, 1);
#endif
/* Kirby code for KIRBYU-3835  at 2024/7/25 start */
/*
	if (nvt_update_firmware(BOOT_UPDATE_FIRMWARE_NAME)) {
		NVT_ERR("download firmware failed, ignore check fw state\n");
	} else {
		nvt_check_fw_reset_state(RESET_STATE_REK);
	}
*/
/* Kirby code for KIRBYU-3835  at 2024/7/25 end */

#if WAKEUP_GESTURE
	nvt_irq_enable(true);
#endif
		if (tp_charge_flag == true) {
				buf[0] = EVENT_MAP_HOST_CMD;
				buf[1] = CMD_CHARGER_ON;
				ret = CTP_SPI_WRITE(ts->client, buf, 2);
			if (ret < 0) {
				NVT_ERR("nvt Write set charger command fail usb!\n");
			} else {
			NVT_LOG("nvt set charger on cmd succeeded usb\n");
			}
		} else {
			buf[0] = EVENT_MAP_HOST_CMD;
			buf[1] = CMD_CHARGER_OFF;
			ret = CTP_SPI_WRITE(ts->client, buf, 2);
			if (ret < 0) {
				NVT_ERR("nvt Write set charger command fail usb\n");
			} else {
				NVT_LOG("nvt set charger off cmd succeeded usb\n");
			}
		}
#if NVT_TOUCH_ESD_PROTECT
	nvt_esd_check_enable(false);
	queue_delayed_work(nvt_esd_check_wq, &nvt_esd_check_work,
			   msecs_to_jiffies(NVT_TOUCH_ESD_CHECK_PERIOD));
#endif /* #if NVT_TOUCH_ESD_PROTECT */

	bTouchIsAwake = 1;

	mutex_unlock(&ts->lock);

#if NVT_CUST_PROC_CMD
	queue_work(nvt_fwu_wq, &ts_restore_cmd_work);
#endif

	NVT_LOG("end\n");

	return 0;
}

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
static int nvt_drm_panel_notifier_callback(struct notifier_block *self,
					   unsigned long event, void *data)
{
	struct drm_panel_notifier *evdata = data;
	int *blank;
	struct nvt_ts_data *ts =
		container_of(self, struct nvt_ts_data, drm_panel_notif);

	if (!evdata)
		return 0;

	if (!(event == DRM_PANEL_EARLY_EVENT_BLANK ||
	      event == DRM_PANEL_EVENT_BLANK)) {
		//NVT_LOG("event(%lu) not need to process\n", event);
		return 0;
	}

	if (evdata->data && ts) {
		blank = evdata->data;
		if (event == DRM_PANEL_EARLY_EVENT_BLANK) {
			if (*blank == DRM_PANEL_BLANK_POWERDOWN) {
				NVT_LOG("event=%lu, *blank=%d\n", event,
					*blank);
				nvt_ts_suspend(&ts->client->dev);
			}
		} else if (event == DRM_PANEL_EVENT_BLANK) {
			if (*blank == DRM_PANEL_BLANK_UNBLANK) {
				NVT_LOG("event=%lu, *blank=%d\n", event,
					*blank);
				nvt_ts_resume(&ts->client->dev);
			}
		}
	}

	return 0;
}
#elif IS_ENABLED(NVT_MSM_DRM_NOTIFY)
static int nvt_drm_notifier_callback(struct notifier_block *self,
				     unsigned long event, void *data)
{
	struct msm_drm_notifier *evdata = data;
	int *blank;
	struct nvt_ts_data *ts =
		container_of(self, struct nvt_ts_data, drm_notif);

	if (!evdata || (evdata->id != 0))
		return 0;

	if (evdata->data && ts) {
		blank = evdata->data;
		if (event == MSM_DRM_EARLY_EVENT_BLANK) {
			if (*blank == MSM_DRM_BLANK_POWERDOWN) {
				NVT_LOG("event=%lu, *blank=%d\n", event,
					*blank);
				nvt_ts_suspend(&ts->client->dev);
			}
		} else if (event == MSM_DRM_EVENT_BLANK) {
			if (*blank == MSM_DRM_BLANK_UNBLANK) {
				NVT_LOG("event=%lu, *blank=%d\n", event,
					*blank);
				nvt_ts_resume(&ts->client->dev);
			}
		}
	}

	return 0;
}
#elif IS_ENABLED(NVT_FB_NOTIFY)
static int nvt_fb_notifier_callback(struct notifier_block *self,
				    unsigned long event, void *data)
{
	struct fb_event *evdata = data;
	int *blank;
	struct nvt_ts_data *ts =
		container_of(self, struct nvt_ts_data, fb_notif);

	if (evdata && evdata->data && event == FB_EARLY_EVENT_BLANK) {
		blank = evdata->data;
		if (*blank == FB_BLANK_POWERDOWN) {
			NVT_LOG("event=%lu, *blank=%d\n", event, *blank);
			nvt_ts_suspend(&ts->client->dev);
		}
	} else if (evdata && evdata->data && event == FB_EVENT_BLANK) {
		blank = evdata->data;
		if (*blank == FB_BLANK_UNBLANK) {
			NVT_LOG("event=%lu, *blank=%d\n", event, *blank);
			nvt_ts_resume(&ts->client->dev);
		}
	}

	return 0;
}
#elif IS_ENABLED(NVT_EARLYSUSPEND_NOTIFY)
/*******************************************************
Description:
	Novatek touchscreen driver early suspend function.

return:
	n.a.
*******************************************************/
static void nvt_ts_early_suspend(struct early_suspend *h)
{
	nvt_ts_suspend(ts->client, PMSG_SUSPEND);
}

/*******************************************************
Description:
	Novatek touchscreen driver late resume function.

return:
	n.a.
*******************************************************/
static void nvt_ts_late_resume(struct early_suspend *h)
{
	nvt_ts_resume(ts->client);
}
#elif IS_ENABLED(NVT_QCOM_PANEL_EVENT_NOTIFY)
static void
nvt_panel_notifier_callback(enum panel_event_notifier_tag tag,
			    struct panel_event_notification *notification,
			    void *client_data)
{
	struct nvt_ts_data *ts = client_data;

	if (!notification) {
		NVT_ERR("Invalid notification\n");
		return;
	}

	NVT_LOG("Notification type:%d, early_trigger:%d",
		notification->notif_type,
		notification->notif_data.early_trigger);

	switch (notification->notif_type) {
	case DRM_PANEL_EVENT_UNBLANK:
		if (notification->notif_data.early_trigger)
			NVT_LOG("resume notification pre commit\n");
		else
			nvt_ts_resume(&ts->client->dev);
		break;

	case DRM_PANEL_EVENT_BLANK:
		if (notification->notif_data.early_trigger)
			nvt_ts_suspend(&ts->client->dev);
		else
			NVT_LOG("suspend notification post commit\n");
		break;

	case DRM_PANEL_EVENT_BLANK_LP:
		NVT_LOG("received lp event\n");
		break;

	case DRM_PANEL_EVENT_FPS_CHANGE:
		NVT_LOG("Received fps change old fps:%d new fps:%d\n",
			notification->notif_data.old_fps,
			notification->notif_data.new_fps);
		break;
	default:
		NVT_LOG("notification serviced :%d\n",
			notification->notif_type);
		break;
	}
}
#elif IS_ENABLED(NVT_MTK_DRM_NOTIFY)
static int nvt_mtk_drm_notifier_callback(struct notifier_block *nb,
					 unsigned long event, void *data)
{
	int *blank = (int *)data;

	if (!blank) {
		NVT_ERR("Invalid blank\n");
		return -1;
	}

	if (event == MTK_DISP_EARLY_EVENT_BLANK) {
		if (*blank == MTK_DISP_BLANK_POWERDOWN) {
			NVT_LOG("event=%lu, *blank=%d\n", event, *blank);
			nvt_ts_suspend(&ts->client->dev);
		}
	} else if (event == MTK_DISP_EVENT_BLANK) {
		if (*blank == MTK_DISP_BLANK_UNBLANK) {
			NVT_LOG("event=%lu, *blank=%d\n", event, *blank);
			nvt_ts_resume(&ts->client->dev);
		}
	}

	return 0;
}
#endif

#if NVT_PM_WAIT_BUS_RESUME_COMPLETE
static int nvt_ts_pm_suspend(struct device *dev)
{
	ts->dev_pm_suspend = true;
#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
	nvt_hall_pm = 1;
#endif
#endif
	reinit_completion(&ts->dev_pm_resume_completion);
	return 0;
}

static int nvt_ts_pm_resume(struct device *dev)
{
	ts->dev_pm_suspend = false;
	complete(&ts->dev_pm_resume_completion);
#ifdef BUILD_LAPIS_TOUCH
#if NVT_HALL_CHECK
	printk("%s:++\n", __func__);
	if (nvt_hall_pm == 1 && nvt_gesture_flag == 1 && nvt_hall_pm_status == 0) {
		if (gpio_get_value(501) == 0) {
			uint8_t buf[4] = {0};
			NVT_LOG("The keyboard still close!");
			buf[0] = EVENT_MAP_HOST_CMD;
			buf[1] = 0x11;
			CTP_SPI_WRITE(ts->client, buf, 2);
			nvt_hall_pm_status = 1;
		}
	}
	printk("%s:--\n", __func__);
#endif
#endif
	return 0;
}

static const struct dev_pm_ops nvt_ts_dev_pm_ops = {
	.suspend = nvt_ts_pm_suspend,
	.resume = nvt_ts_pm_resume,
};
#endif /* NVT_PM_WAIT_BUS_RESUME_COMPLETE */

static const struct spi_device_id nvt_ts_id[] = {
	{ NVT_SPI_NAME, 0 },
	{ "NVT-ts-spi", 0 },
	{}
};
MODULE_DEVICE_TABLE(spi, nvt_ts_id);

#ifdef CONFIG_OF
static struct of_device_id nvt_match_table[] = {
	{
		.compatible = "novatek,NVT-ts-spi",
	},
	{},
};
#endif

MODULE_DEVICE_TABLE(of, nvt_match_table);

static struct spi_driver nvt_spi_driver = {
	.probe		= nvt_ts_probe,
	.remove		= nvt_ts_remove,
	.shutdown	= nvt_ts_shutdown,
	.id_table	= nvt_ts_id,
	.driver = {
		.name	= NVT_SPI_NAME,
		.owner	= THIS_MODULE,
#ifdef CONFIG_OF
		.of_match_table = nvt_match_table,
#endif
#if NVT_PM_WAIT_BUS_RESUME_COMPLETE
		.pm = &nvt_ts_dev_pm_ops,
#endif /* NVT_PM_WAIT_BUS_RESUME_COMPLETE */
	},
};

// Linux 2.0/2.2
static int penraw_open(struct inode * inode, struct file * file)
{
  return 0;
}

// Linux 2.1: int type
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2, 1, 0)
static int penraw_close(struct inode * inode, struct file * file)
{
       return 0;
}
#else
static void penraw_close(struct inode * inode, struct file * file)
{
}
#endif

#define PENRAW_IOC_TYPE 'P'
#define PENRAW_GET_VALUES _IOR(PENRAW_IOC_TYPE, 0, struct io_pen_report)

static struct io_pen_report pen_report;        // return report
static long penraw_ioctl(struct file *file,
             unsigned int cmd, unsigned long arg)
{
       int len = 0;
       unsigned long   flags;
       struct lenovo_pen_info *ppen_info;
       unsigned char cnt;
       unsigned char pen_buffer_rp;
       unsigned char wp;
       unsigned char num;

//     printk(KERN_ERR "penraw: ioctl: cmd=%04X, arg=%08lX\n",cmd,arg);


	switch(cmd)
	{
		case PENRAW_GET_VALUES:
			local_irq_save(flags);
			wp = pen_buffer_wp;
			num = pen_report_num;
			local_irq_restore(flags);
			if(MAX_IO_CONTROL_REPORT <= num) {
				pen_buffer_rp = (unsigned char)((wp + (LENOVO_MAX_BUFFER - MAX_IO_CONTROL_REPORT)) % LENOVO_MAX_BUFFER);
			} else {
				pen_buffer_rp = 0;
			}
			memset(&pen_report, 0, sizeof(pen_report));
			pen_report.report_num = num;
			ppen_info = (struct lenovo_pen_info *)&pen_report.pen_info[0];
			for(cnt = 0; cnt < num; cnt++) {
				memcpy(ppen_info, &pen_buffer[pen_buffer_rp], sizeof(struct lenovo_pen_info));
				ppen_info++;
				pen_buffer_rp++;
				if(LENOVO_MAX_BUFFER == pen_buffer_rp) {
					pen_buffer_rp = 0;
				}
			}
			if (copy_to_user((void __user *)arg, &pen_report, sizeof(pen_report))) {
				return -EFAULT;
			}
			break;
		default:
			printk(KERN_WARNING "unsupported command %d\n", cmd);
			return -EFAULT;
       }
	return len;
}

static struct file_operations penraw_fops = {
	.owner = THIS_MODULE,
	.open = penraw_open,
	.release = penraw_close,
	.unlocked_ioctl = penraw_ioctl,
};

/*******************************************************
Description:
	Driver Install function.

return:
	Executive Outcomes. 0---succeed. not 0---failed.
********************************************************/
static int32_t __init nvt_driver_init(void)
{
	int32_t ret = 0;
	int alloc_ret;
	dev_t dev;
	int cdev_err;

#ifdef BUILD_KIRBY_TOUCH
	NVT_LOG("nvt_36523n start\n");
#else
	NVT_LOG("nvt_36532 start\n");
#endif

/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 start */
	gpio_direction_input(DISP_ID_DET);
	gpio_125 = gpio_get_value(DISP_ID_DET);
	NVT_LOG("gpio_125 = %d", gpio_125);
	if ((gpio_125 != 0) && (gpio_125!= 1)) {
	    NVT_LOG("TP is not NVT\n");
		return 0;
	}
/* Kirby code for KIRBYU-235 by liaoxg1 at 2024/4/26 end */
	//---add spi driver---
	ret = spi_register_driver(&nvt_spi_driver);
	if (ret) {
		NVT_ERR("failed to add spi driver");
		goto err_driver;
	}

	pen_report_num = 0;
	pen_frame_no = 0;
	pen_buffer_wp = 0;

	/* get not assigned major numbers */
	alloc_ret = alloc_chrdev_region(&dev, MINOR_NUMBER_START, NUMBER_MINOR_NUMBER, PENRAW_DRIVER_NAME);
	if (alloc_ret != 0) {
		printk(KERN_ERR "failed to alloc_chrdev_region()\n");
		return -EINVAL;
	}

	/* get one number from the not-assigend numbers */
	major_number = MAJOR(dev);

	/* initialize cdev and function table */
	cdev_init(&penraw_char_dev, &penraw_fops);
	penraw_char_dev.owner = THIS_MODULE;

	/* register the driver */
	cdev_err = cdev_add(&penraw_char_dev, dev, NUMBER_MINOR_NUMBER);
	if (cdev_err != 0) {
		printk(KERN_ERR "failed to cdev_add()\n");
		unregister_chrdev_region(dev, NUMBER_MINOR_NUMBER);
		return -EINVAL;
	}

	/* register a class */
	penraw_char_dev_class = class_create(PENRAW_DEVICE_NAME);
	if (IS_ERR(penraw_char_dev_class)) {
		printk(KERN_ERR "class_create()\n");
		cdev_del(&penraw_char_dev);
		unregister_chrdev_region(dev, NUMBER_MINOR_NUMBER);
		return -EINVAL;
	}

	/* create "/sys/class/my_device/my_device" */
	device_create(penraw_char_dev_class, NULL, MKDEV(major_number, 0), NULL, PENRAW_DEVICE_NAME);

#ifdef BUILD_KIRBY_TOUCH
	NVT_LOG("nvt_36523n finished\n");
#else
	NVT_LOG("nvt_36532 start\n");
#endif

err_driver:
	return ret;
}

/*******************************************************
Description:
	Driver uninstall function.

return:
	n.a.
********************************************************/
static void __exit nvt_driver_exit(void)
{
	dev_t dev = MKDEV(major_number, MINOR_NUMBER_START);

	spi_unregister_driver(&nvt_spi_driver);
	/* remove "/dev/lenovo_penraw */
	device_destroy(penraw_char_dev_class, MKDEV(major_number, 0));

	/* remove class */
	class_destroy(penraw_char_dev_class);

	/* remove driver */
	cdev_del(&penraw_char_dev);

	/* release the major number */
	unregister_chrdev_region(dev, NUMBER_MINOR_NUMBER);

}

#if IS_ENABLED(NVT_DRM_PANEL_NOTIFY)
late_initcall(nvt_driver_init);
#else
module_init(nvt_driver_init);
#endif
module_exit(nvt_driver_exit);

MODULE_DESCRIPTION("Novatek Touchscreen Driver");
MODULE_LICENSE("GPL");
/* TB710FU: built-in build does not need the vendor VFS import namespace */
