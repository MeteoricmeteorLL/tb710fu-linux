#ifndef 	_LINUX_NVT_TOUCH_H
#define		_LINUX_NVT_TOUCH_H

#include <linux/delay.h>
#include <linux/input.h>
#include <linux/of.h>
#include <linux/spi/spi.h>
#include <linux/uaccess.h>
#include <linux/version.h>
#include <linux/power_supply.h>


#define NVT_CUST_PROC_CMD 1
#define NVT_EDGE_GRID_ZONE 1
#define NVT_WAKEUP_GESTURE_CUSTOMIZE 1


#define NVT_EXT_CMD 0x7F
#define NVT_EXT_CMD_EDGE_GRID_ZONE 0x01


#define NVT_USB_DETECT_GLOBAL 1
#if NVT_USB_DETECT_GLOBAL
#define USB_DETECT_IN 1
#define USB_DETECT_OUT 0
#define CMD_CHARGER_ON (0x53)
#define CMD_CHARGER_OFF (0x51)
#endif

#if NVT_CUST_PROC_CMD
	int32_t edge_reject_state;
	struct edge_grid_zone_info edge_grid_zone_info;
	uint8_t game_mode_state;
	uint8_t pen_state;
	uint8_t probe_state;
#endif



#if NVT_CUST_PROC_CMD
struct edge_grid_zone_info {
    uint8_t degree;
    uint8_t direction;
    uint16_t y1;
    uint16_t y2;
};
#endif


struct edge_grid_zone_info edge_grid_zone_info;



typedef enum {
    EVENT_MAP_HOST_CMD                      = 0x50,
    EVENT_MAP_HANDSHAKING_or_SUB_CMD_BYTE   = 0x51,
    EVENT_MAP_RESET_COMPLETE                = 0x60,
    EVENT_MAP_FWINFO                        = 0x78,
    EVENT_MAP_PROJECTID                     = 0x9A,
} SPI_EVENT_MAP;



//---extern functions---
int32_t CTP_SPI_READ(struct spi_device *client, uint8_t *buf, uint16_t len);
int32_t CTP_SPI_WRITE(struct spi_device *client, uint8_t *buf, uint16_t len);
int32_t nvt_set_page(uint32_t addr);




#endif /* _LINUX_NVT_TOUCH_H */
