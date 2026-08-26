# Theos 构建文件
# 前提：装好 Theos（https://theos.dev/docs/installation）
#
#   make package                     # 生成 .deb
#   make package FINALPACKAGE=1      # 发布版
#   make do                          # 编译 + 安装到 THEOS_DEVICE_IP 指定的设备

TARGET := iphone:clang:latest:14.0
ARCHS = arm64 arm64e
INSTALL_TARGET_PROCESSES = WeChat

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = WXAutoReply

WXAutoReply_FILES = Tweak.x
WXAutoReply_CFLAGS = -fobjc-arc -Wno-deprecated-declarations
WXAutoReply_FRAMEWORKS = UIKit Foundation

include $(THEOS_MAKE_PATH)/tweak.mk
