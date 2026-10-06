/*
 * Copyright (C) 2010 - 2022 Novatek, Inc.
 *
 * $Revision: 120904 $
 * $Date: 2023-06-26 09:57:11 +0800 (週一, 26 六月 2023) $
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

#include <linux/of.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include "nt36xxx.h"

#if IS_ENABLED(NVT_PLATFORM_DRIVER)

extern int ts_touch_info_uevent(const struct device *dev, struct kobj_uevent_env *env);
const struct device_type tp_dev_type ={
	.name ="novatek_ts",
	.uevent= ts_touch_info_uevent,
};

static int32_t nvt_ts_platform_probe(struct platform_device *pdev)
{
	int32_t ret = 0;

	NVT_LOG("start\n");

	pdev->dev.type = &tp_dev_type;

	NVT_LOG("end\n");

	return ret;
}

static const struct platform_device_id nvt_ts_platform_id[] = {
    {.name = NVT_PLATFORM_DRIVER_NAME},
    {}
};
MODULE_DEVICE_TABLE(platform, nvt_ts_platform_id);

static struct platform_driver nvt_platform_driver = {
	.driver = {
		.name = NVT_PLATFORM_DRIVER_NAME,
		.owner = THIS_MODULE,
	},
	.probe = nvt_ts_platform_probe,
	.id_table	= nvt_ts_platform_id,
};

int32_t nvt_ts_platform_driver_init(void)
{
	NVT_LOG("enter\n");
	return platform_driver_register(&nvt_platform_driver);
}
#endif
