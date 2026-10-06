#include "nt36xxx.h"
#include "nvt_common.h"
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/interrupt.h>
#include <linux/irq.h>
#include <linux/gpio.h>
#include <linux/proc_fs.h>
#include <linux/input/mt.h>
#include <linux/input/touch_common.h>
#include <linux/of_gpio.h>
#include <linux/of_irq.h>



#include <linux/notifier.h>
#include <linux/fb.h>

#define EDGE_GRID_ZONE "edge_grid_zone"
#define GESTURE_CONTROL "gesture_control"


static struct proc_dir_entry *NVT_proc_edge_grid_zone_entry;
static struct proc_dir_entry *NVT_proc_gesture_entry;




/*******************************************************
*Description:
*Touchscreen common function proc. file node
*initial function.
*
*******************************************************/

int32_t nvt_common_proc_init(void)
{

	NVT_proc_edge_grid_zone_entry = proc_create(EDGE_GRID_ZONE, 0644, NULL, &nvt_edge_grid_zone_fops);
	if (NVT_proc_edge_grid_zone_entry == NULL) {
		NVT_ERR("create proc/%s Failed!\n", EDGE_GRID_ZONE);
		return -ENOMEM;
	} else {
		NVT_DBG("create proc/%s Succeeded!\n", EDGE_GRID_ZONE);
	}

	NVT_proc_gesture_entry = proc_create(GESTURE_CONTROL, 0644, NULL, &nvt_gesture_fops);
	if (NVT_proc_gesture_entry == NULL) {
		NVT_ERR("create proc/gesture_control Failed!\n");
		return -ENOMEM;
	} else {
		NVT_DBG("create proc/gesture_control Succeeded!\n");
	}

	return 0;
}



/*******************************************************
*Description:
*Touchscreen common function proc. file node
*deinitial function.
*
*******************************************************/

int32_t nvt_common_proc_deinit(void)
{
	if (NVT_proc_edge_grid_zone_entry != NULL) {
		remove_proc_entry(EDGE_GRID_ZONE, NULL);
		NVT_proc_edge_grid_zone_entry = NULL;
		NVT_LOG("Removed /proc/%s \n", EDGE_GRID_ZONE);
	}

	if (NVT_proc_gesture_entry != NULL) {
		remove_proc_entry("gesture_control", NULL);
		NVT_proc_gesture_entry = NULL;
		NVT_LOG("Removed /proc/gesture_control \n");
	}

}



/*******************************************************
*Description:
*Touchscreen common nvt_edge_grid_zone function.
*
*******************************************************/

int32_t nvt_edge_grid_zone_set(uint8_t deg, uint8_t dir, uint16_t y1, uint16_t y2)
{
    int i, retry = 5;
    uint8_t buf[12] = {0};
#define NVT_EXT_CMD 0x7F
#define NVT_EXT_CMD_EDGE_GRID_ZONE 0x01

    //---set xdata index to EVENT BUF ADDR---(set page)
    nvt_set_page(ts->mmap->EVENT_BUF_ADDR);

    for (i = 0; i < retry; i++) {
        /*---set cmd status---*/
        buf[0] = EVENT_MAP_HOST_CMD;
        buf[1] = NVT_EXT_CMD;
        buf[2] = NVT_EXT_CMD_EDGE_GRID_ZONE;
        buf[3] = deg;
        buf[4] = dir;
        buf[5] = (uint8_t) (y1 & 0xFF);
        buf[6] = (uint8_t) ((y1 >> 8) & 0xFF);
        buf[7] = (uint8_t) (y2 & 0xFF);
        buf[8] = (uint8_t) ((y2 >> 8) & 0xFF);
        CTP_SPI_WRITE(ts->client, buf, 9);
        

        msleep(20);

        //---read cmd status---
        buf[0] = EVENT_MAP_HOST_CMD;
        buf[1] = 0xFF;
        buf[2] = 0xFF;
        buf[3] = 0xFF;
        buf[4] = 0xFF;
        buf[5] = 0xFF;
        buf[6] = 0xFF;
        buf[7] = 0xFF;
        buf[8] = 0xFF;
        CTP_SPI_READ(ts->client, buf, 9);
        if (buf[1] == 0x00)
            break;
    }

    if (unlikely(i == retry)) {
        NVT_ERR("send Cmd 0x%02X 0x%02X failed, buf[1]=0x%02X\n",
            NVT_EXT_CMD, NVT_EXT_CMD_EDGE_GRID_ZONE, buf[1]);
        return -1;
    } else {
        NVT_LOG("send Cmd 0x%02X 0x%02X success, tried %d times\n",
            NVT_EXT_CMD, NVT_EXT_CMD_EDGE_GRID_ZONE, i);
    }

    return 0;
}
static ssize_t nvt_edge_grid_zone_store(struct file *file, const char *buffer, size_t count, loff_t *pos) {
    int32_t tmp[4];
    uint8_t ret;
    char buf[16] = { 0 };

    ret = copy_from_user(buf, (uint8_t *) buffer, count);
    if (ret)
        return -EINVAL;

    NVT_LOG("buf=%s\n", buf);

    ret = sscanf(buf, "%d,%d,%d,%d",
        tmp, tmp+1, tmp+2, tmp+3);

    ts->edge_grid_zone_info.degree = (uint8_t) tmp[0];
    ts->edge_grid_zone_info.direction = (uint8_t) tmp[1];
    ts->edge_grid_zone_info.y1 = (uint16_t) tmp[2];
    ts->edge_grid_zone_info.y2 = (uint16_t) tmp[3];

    NVT_LOG("cmd_parm = %d,%d,%d,%d\n",
        ts->edge_grid_zone_info.degree,
        ts->edge_grid_zone_info.direction,
        ts->edge_grid_zone_info.y1,
        ts->edge_grid_zone_info.y2);

    nvt_edge_grid_zone_set(ts->edge_grid_zone_info.degree,
        ts->edge_grid_zone_info.direction,
        ts->edge_grid_zone_info.y1,
        ts->edge_grid_zone_info.y2);

	return count;
}
static int nvt_edge_grid_zone_show(struct seq_file *sfile, void *v) {
    seq_printf(sfile, "%d,%d,%d,%d",
        ts->edge_grid_zone_info.degree,
        ts->edge_grid_zone_info.direction,
        ts->edge_grid_zone_info.y1,
        ts->edge_grid_zone_info.y2);
    return 0;
}
static int32_t nvt_edge_grid_zone_open(struct inode *inode, struct file *file) {
	return single_open(file, nvt_edge_grid_zone_show, NULL);
}


static const struct proc_ops nvt_edge_grid_zone_fops = {
	.proc_open = nvt_edge_grid_zone_open,
	.proc_read = seq_read,
	.proc_write = nvt_edge_grid_zone_store,
	.proc_lseek = seq_lseek,
	.proc_release = seq_release,

};

/*******************************************************
*Description:
*Touchscreen common nvt_gesture function.
*Tp double click wake up function.
*
*******************************************************/
int gesture_flag = 0;
int get_gesture_flag(void)
{
	return gesture_flag;
}
EXPORT_SYMBOL(get_gesture_flag);


static int nvt_gesture_show(struct seq_file *sfile, void *v) {
	if (ts->gesture_enabled)
		seq_printf(sfile, "Enable Gesture!\n");
	else
		seq_printf(sfile, "Disable Gesture!\n");

	return 0;
}

static ssize_t nvt_gesture_store(struct file *file, const char *buffer, size_t count, loff_t *pos) {
	char dbg[10] = { 0 };
	int res = 0;
	uint8_t state;

	res = copy_from_user(dbg, (uint8_t *) buffer, sizeof(uint8_t));
	if (res)
		return -EINVAL;

	res = kstrtou8(dbg, 16, &state);
	if (res < 0)
		return res;

	if (state == 0)
		ts->gesture_enabled = false;
	else
		ts->gesture_enabled = true;

	gesture_flag = ts->gesture_enabled;

	return count;

}
static int32_t nvt_gesture_open(struct inode *inode, struct file *file) {
	return single_open(file, nvt_gesture_show, NULL);
}

static const struct proc_ops nvt_gesture_fops = {
	.proc_open = nvt_gesture_open,
	.proc_read = seq_read,
	.proc_write = nvt_gesture_store,
	.proc_lseek = seq_lseek,
	.proc_release = seq_release,
};


/*******************************************************
*Description:
*Touchscreen common double click wake up gesture key
*report function.
*
*nvt_ts_work_func--->nvt_ts_wakeup_gesture_report_customize
*
*******************************************************/

#if NVT_WAKEUP_GESTURE_CUSTOMIZE
/* customized gesture id */
#define DATA_PROTOCOL           30
/* function page definition */
#define FUNCPAGE_GESTURE         1

#define GESTURE_DOUBLE_CLICK    15

void nvt_ts_wakeup_gesture_report_customize(uint8_t gesture_id, uint8_t *data)
{
	uint32_t keycode = 0;
	uint8_t func_type = data[2];
	uint8_t func_id = data[3];

	/* support fw specifal data protocol */
	if ((gesture_id == DATA_PROTOCOL) && (func_type == FUNCPAGE_GESTURE)) {
		gesture_id = func_id;
	} else if (gesture_id > DATA_PROTOCOL) {
		NVT_ERR("gesture_id %d is invalid, func_type=%d, func_id=%d\n", gesture_id, func_type, func_id);
		return;
	}

	NVT_LOG("gesture_id = %d\n", gesture_id);

	switch (gesture_id) {
		case GESTURE_DOUBLE_CLICK:
			NVT_LOG("Gesture : Double Click.\n");
			keycode = gesture_key_array[3];
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
*Description:
*Touchscreen common charge state prevents touching false
*positives  function.
*
*nvt_ts_probe--->nvt_charger_init
*
*******************************************************/


#if NVT_USB_DETECT_GLOBAL
static int32_t nvt_set_charger(uint8_t charger_on_off){
	uint8_t buf[8] = {0};
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

static void nvt_charger_notify_work(struct work_struct *work)
{
	if (NULL == work) {
		NVT_ERR("%s:  parameter work are null!\n", __func__);
		return;
	}

	NVT_LOG("enter nvt_charger_notify_work\n");

	if (USB_DETECT_IN == ts->usb_plug_status) {
		NVT_LOG("USB plug in");
		nvt_set_charger(USB_DETECT_IN);
	} else if (USB_DETECT_OUT == ts->usb_plug_status) {
		NVT_LOG("USB plug out");
		nvt_set_charger(USB_DETECT_OUT);
	}else{
		NVT_LOG("Charger flag:%d not currently required!\n",ts->usb_plug_status);
	}

}

static int nvt_charger_notifier_callback(struct notifier_block *nb,unsigned long val, void *v)
{
	int ret = 0;
	struct power_supply *psy = NULL;
	union power_supply_propval prop;
	struct nvt_ts_data *ts = container_of(nb, struct nvt_ts_data, charger_notif);

	psy = power_supply_get_by_name("usb");
	if (!psy) {
		NVT_ERR("Couldn't get usbpsy\n");
		return -EINVAL;
	}
	if (!strcmp(psy->desc->name, "usb")) {
		if (psy && ts && val == POWER_SUPPLY_PROP_STATUS) {
			ret = power_supply_get_property(psy, POWER_SUPPLY_PROP_ONLINE, &prop);
			if (ret < 0) {
				NVT_ERR("Couldn't get POWER_SUPPLY_PROP_ONLINE rc=%d\n", ret);
				return ret;
			} else {
				if(prop.intval != ts->usb_plug_status) {
					NVT_LOG("usb_plug_status = %d\n", prop.intval);
					ts->usb_plug_status = prop.intval;
					if( bTouchIsAwake && (ts->nvt_charger_notify_wq != NULL))
						queue_work(ts->nvt_charger_notify_wq, &ts->charger_notify_work);
				}
			}
		}
	}
	return 0;
}

void nvt_charger_init(void)
{
	int ret = 0;
	struct power_supply *psy = NULL;
	union power_supply_propval prop;

	ts->usb_plug_status = 0;
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


/*******************************************************
*Description:
*Touchscreen common edge reject  function.
*
*
*******************************************************/
#if NVT_CUST_PROC_CMD
int32_t nvt_cmd_store(uint8_t u8Cmd){
	int i, retry = 5;
	uint8_t buf[3] = {0};
	int32_t ret = 0;

	if (mutex_lock_interruptible(&ts->lock)) {
		return -ERESTARTSYS;
	}
	//---set xdata index to EVENT BUF ADDR---
	ret = nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_HOST_CMD);
	if (ret < 0) {
		NVT_ERR("Set event buffer index fail!\n");
		mutex_unlock(&ts->lock);
		return ret;
	}

	for (i = 0; i < retry; i++) {
		//---set cmd status---
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = u8Cmd;
		CTP_SPI_WRITE(ts->client, buf, 2);
		msleep(20);
		//---read cmd status---
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = 0xFF;
		CTP_SPI_READ(ts->client, buf, 2);
		if (buf[1] == 0x00)
			break;
	}

	if (unlikely(i == retry)) {
		NVT_LOG("send Cmd 0x%02X failed, buf[1]=0x%02X\n", u8Cmd, buf[1]);
		ret = -1;
	} else {
		NVT_LOG("send Cmd 0x%02X success, tried %d times\n", u8Cmd, i);
	}

	mutex_unlock(&ts->lock);

	return ret;
}
int32_t nvt_ext_cmd_store(uint8_t u8Cmd, uint8_t u8subCmd){
	int i, retry = 5;
	uint8_t buf[4] = {0};
	int32_t ret = 0;

	if (mutex_lock_interruptible(&ts->lock)) {
		return -ERESTARTSYS;
	}

	//---set xdata index to EVENT BUF ADDR---
	ret = nvt_set_page(ts->mmap->EVENT_BUF_ADDR | EVENT_MAP_HOST_CMD);
	if (ret < 0) {
		NVT_ERR("Set event buffer index fail!\n");
		mutex_unlock(&ts->lock);
		return ret;
	}

	for (i = 0; i < retry; i++) {
		//---set cmd status---
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = u8Cmd;
		buf[2] = u8subCmd;
		CTP_SPI_WRITE(ts->client, buf, 3);

		msleep(20);

		//---read cmd status---
		buf[0] = EVENT_MAP_HOST_CMD;
		buf[1] = 0xFF;
		CTP_SPI_READ(ts->client, buf, 2);
		if (buf[1] == 0x00)
			break;
	}

	if (unlikely(i == retry)) {
		NVT_LOG("send Cmd 0x%02X 0x%02X failed, buf[1]=0x%02X\n", u8Cmd, u8subCmd, buf[1]);
		ret = -1;
	} else {
		NVT_LOG("send Cmd 0x%02X 0x%02X success, tried %d times\n", u8Cmd, u8subCmd, i);
	}

	mutex_unlock(&ts->lock);

	return ret;
}

/*
 *	/proc/panel_angle cmd_param
 *      [0], 0 : panel rotate 0 degree
 *			 1 : panel rotate 90 degree
 *			 2 : panel rotate 180 degree
 *			 3 : panel rotate 270 degree
 *
 */
int32_t nvt_edge_reject_set(int32_t status) {
	int ret = 0;

	if(status == 0)//rotate 0 degree
		ret = nvt_cmd_store(EDGE_REJECT_VERTICLE_CMD);
	else if(status == 1) //rotate 90 degree
		ret = nvt_cmd_store(EDGE_REJECT_RIGHT_UP);
	else if(status == 2) //rotate 180 degree
		ret = nvt_cmd_store(EDGE_REJECT_VERTICLE_REVERSE_CMD);
	else if(status == 3) //rotate 270 degree
		ret = nvt_cmd_store(EDGE_REJECT_LEFT_UP);

	return ret;
}

static ssize_t nvt_edge_reject_store(struct file *file, const char *buffer, size_t count, loff_t *pos) {
	char dbg[10] = { 0 };
	int res = 0;
	uint8_t state;
	
	res = copy_from_user(dbg, (uint8_t *) buffer, sizeof(uint8_t));
	if (res)
		return -EINVAL;

	res = kstrtou8(dbg, 16, &state);
	if (res < 0)
		return res;

	ts->edge_reject_state = state;
		
	nvt_edge_reject_set(ts->edge_reject_state);

	return count;
}

static int nvt_edge_reject_show(struct seq_file *sfile, void *v) {
	
	if(ts->edge_reject_state == 0)
		seq_printf(sfile, "Vertical Direction!(0 degree)\n"); //rotate 0 degree
	else if(ts->edge_reject_state == 1)
		seq_printf(sfile, "Right Up Direction!(90 degree)\n"); //rotate 90 degree
	else if(ts->edge_reject_state == 2)
		seq_printf(sfile, "Vertical reverse Direction!(180 degree)\n"); //rotate 180 degree
	else if(ts->edge_reject_state == 3)
		seq_printf(sfile, "Left Up Direction!(270 degree)\n"); //rotate 270 degree
	else
		seq_printf(sfile, "Not Support!\n");

	return 0;
}

static int32_t nvt_edge_reject_open(struct inode *inode, struct file *file) {
	return single_open(file, nvt_edge_reject_show, NULL);
}


#ifdef HAVE_PROC_OPS
static const struct proc_ops nvt_edge_reject_fops = {
	.proc_open = nvt_edge_reject_open,
	.proc_read = seq_read,
	.proc_write = nvt_edge_reject_store,
	.proc_lseek = seq_lseek,
	.proc_release = seq_release,
};
#else
static const struct file_operations nvt_edge_reject_fops = {
	.owner = THIS_MODULE,
	.open = nvt_edge_reject_open,
	.read = seq_read,
	.write = nvt_edge_reject_store,
	.llseek = seq_lseek,
	.release = seq_release,
};
#endif




/*
 *	/proc/game_mode cmd_param
 *      [0], 0 : normal mode
 *			 1 : pen mode(enhance palm reject)
 *			 2 : game mode(remove palm reject)
 *
 */
int32_t nvt_game_mode_set(uint8_t status) {
	int ret = 0;

	if(status == 0)
		ret = nvt_ext_cmd_store(GAME_MODE_PALM_CMD, GAME_MODE_NORMAL);
	else if(status == 2)
		ret = nvt_ext_cmd_store(GAME_MODE_PALM_CMD, GAME_MODE_REMOVE);
	else if(status == 1)
		ret = nvt_ext_cmd_store(GAME_MODE_PALM_CMD, GAME_MODE_ENHANCE);


	return ret;
}
static ssize_t nvt_game_mode_store(struct file *file, const char *buffer, size_t count, loff_t *pos) {
	char dbg[10] = { 0 };
	uint8_t state;
	uint8_t ret;
	
	ret = copy_from_user(dbg, (uint8_t *) buffer, sizeof(uint8_t));
	if (ret)
		return -EINVAL;

	ret = kstrtou8(dbg, 16, &state);
	if (ret < 0)
		return ret;

	NVT_LOG("moto_apk_state %d!\n", state);
	ts->game_mode_state = state;
	nvt_game_mode_set(ts->game_mode_state);

	return count;
}
static int nvt_game_mode_show(struct seq_file *sfile, void *v) {
	seq_printf(sfile, "%d\n", ts->game_mode_state);
	return 0;
}
static int32_t nvt_game_mode_open(struct inode *inode, struct file *file) {
	return single_open(file, nvt_game_mode_show, NULL);
}

#ifdef HAVE_PROC_OPS
static const struct proc_ops nvt_game_mode_fops = {
	.proc_open = nvt_game_mode_open,
	.proc_read = seq_read,
	.proc_write = nvt_game_mode_store,
	.proc_lseek = seq_lseek,
	.proc_release = seq_release,

};

#else
static const struct file_operations nvt_game_mode_fops = {
	.owner = THIS_MODULE,
	.open = nvt_game_mode_open,
	.read = seq_read,
	.write = nvt_game_mode_store,
	.llseek = seq_lseek,
	.release = seq_release,
};
#endif











