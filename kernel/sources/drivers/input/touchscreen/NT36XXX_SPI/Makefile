#
# Makefile for the Novatek NT36xxx touchscreen driver.
#

# Each configuration option enables a list of files.
ENV_VARIABLE_FILE := $(abspath ../../../../../../../../../../../../../env_variable.txt)
HQ_TARGET_PRODUCT := $(shell grep "HQ_TARGET_PRODUCT" $(ENV_VARIABLE_FILE) | cut -d'=' -f2)
$(info touch get HQ_TARGET_PRODUCT: $(HQ_TARGET_PRODUCT) from ENV_VARIABLE_FILE: $(ENV_VARIABLE_FILE))

ifeq ($(HQ_TARGET_PRODUCT), $(filter $(HQ_TARGET_PRODUCT), kirby_row kirby_prc))
EXTRA_CFLAGS += -DBUILD_KIRBY_TOUCH
else ifeq ($(HQ_TARGET_PRODUCT), $(filter $(HQ_TARGET_PRODUCT), lapis_row lapis_prc))
EXTRA_CFLAGS += -DBUILD_LAPIS_TOUCH
endif

obj-$(CONFIG_TOUCHSCREEN_NT36XXX_SPI) += nvt_36xxx.o
nvt_36xxx-y +=  nt36xxx.o
nvt_36xxx-y +=  nt36xxx_fw_update.o
nvt_36xxx-y +=  nt36xxx_ext_proc.o
nvt_36xxx-y +=  nt36xxx_mp_ctrlram.o
nvt_36xxx-y +=  nt36xxx_platform.o
