#!/usr/bin/env python3
# TB710FU: reach the loader. Run R-array up to (not incl.) initr_dm_devices,
# then actively probe the UCLASS_VIDEO and UCLASS_SCSI devices, init the
# console, and jump to the loader. This avoids dm_autoprobe() over all
# drivers while still bringing up video + storage.
f = '/home/meteor/u-boot-13r/common/board_r.c'
s = open(f).read()

old = '''	/* Console via simple_video (framebuffer @0xD5100000). */
	stdio_init_tables();
	{
		int rc = console_init_f();
		(void)rc;
	}'''
new = '''	/* Actively probe the video (console) and SCSI/UFS devices we need,
	 * instead of dm_autoprobe() over every driver. */
	{
		struct udevice *dv, *sv;
		int rc;

		rc = uclass_first_device_err(UCLASS_VIDEO, &dv);
		rc = uclass_first_device_err(UCLASS_SCSI, &sv);
		(void)rc;
		(void)dv;
		(void)sv;
	}

	stdio_init_tables();
	{
		int rc = console_init_f();
		(void)rc;
	}'''
assert old in s, 'video init anchor not found'
s = s.replace(old, new, 1)
if '#include <dm/uclass.h>' not in s:
    s = s.replace('#include <init.h>', '#include <init.h>\n#include <dm/uclass.h>', 1)
open(f, 'w').write(s)
print('active video+scsi probe installed')