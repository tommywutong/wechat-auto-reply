"""iOS 微信自动回复 —— 非越狱方案（Appium + WebDriverAgent）。

这是未越狱 iPhone 上唯一可行的路子：不注入微信、不读它的数据库，
而是像一只手一样去点屏幕。iOS 沙盒禁止任何第三方 App 读取微信消息，
所以「UI 自动化」是绕不开的天花板，不是我们偷懒。

运行前提（缺一不可）：
  1. 一台 Mac，装好 Xcode + Command Line Tools
  2. appium + appium-xcuitest-driver
  3. 一台真机 iPhone（模拟器上装不了 App Store 版微信）
  4. WebDriverAgent 已用你的开发者证书签名并跑在手机上
  5. 微信保持前台或至少已登录

详细步骤见 ios/appium/README.md。

用法：
    export WXAUTO_SERVER=http://127.0.0.1:8848
    export WXAUTO_TOKEN=<和服务端一致>
    export IOS_UDID=$(idevice_id -l | head -1)
    python ios/appium/wechat_ios_bot.py --dry-run   # 先干跑，只打印不发送
    python ios/appium/wechat_ios_bot.py            # 确认没问题再真发
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

import requests
from appium import webdriver
from appium.options.ios import XCUITestOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, WebDriverException

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("wechat-ios")

WECHAT_BUNDLE_ID = "com.tencent.xin"

# 微信 iOS 没有稳定的 accessibility-id，只能靠可见文案定位，
# 而文案随语言和版本变。这里集中放在一处，换版本时只改这里。
SELECTORS = {
    "tab_chats": "微信",          # 底部第一个 tab
    "send_button": "发送",
    "input_placeholder": "输入",   # 输入框的 placeholder 前缀
    "back_button": "微信",        # 聊天页左上角返回
}

# 会话列表里未读徽标的文案形如 "3" 或 "99+"
UNREAD_BADGE = re.compile(r"^\d+\+?$")


@dataclass
class ChatPreview:
    name: str
    unread: int
    element: object  # XCUIElement，供点击


class EngineClient:
    """跟本地规则服务通信。网络挂了就当作「不回」，绝不瞎发。"""

    def __init__(
        self, base_url: str, token: str, account: str = "", timeout: float = 10.0
    ) -> None:
        self._url = base_url.rstrip("/") + "/reply"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._account = account
        self._timeout = timeout

    def decide(self, chat_name: str, text: str, is_group: bool, mentioned_me: bool) -> Optional[dict]:
        payload = {
            "chat_id": f"ios:{chat_name}",
            "chat_name": chat_name,
            "text": text,
            "sender_name": chat_name,
            "is_group": is_group,
            "mentioned_me": mentioned_me,
            "platform": "ios",
            "account": self._account,
        }
        try:
            resp = requests.post(
                self._url, json=payload, headers=self._headers, timeout=self._timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("规则服务不可用，本轮跳过: %s", exc)
            return None


class WeChatIOSBot:
    def __init__(self, driver, engine: EngineClient, dry_run: bool = False) -> None:
        self.driver = driver
        self.engine = engine
        self.dry_run = dry_run

    # ------------------------------------------------------------- 页面操作

    def _find_by_label(self, label: str, partial: bool = False):
        if partial:
            query = f'**/XCUIElementTypeAny[`label CONTAINS "{label}"`]'
        else:
            query = f'**/XCUIElementTypeAny[`label == "{label}"`]'
        return self.driver.find_element(AppiumBy.IOS_CLASS_CHAIN, query)

    def ensure_chat_list(self) -> bool:
        """回到会话列表页。已经在列表页时是空操作。"""
        for _ in range(3):
            try:
                # 聊天页有输入框；有输入框说明还在会话里，先返回
                self.driver.find_element(
                    AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeTextView"
                )
                self._tap_back()
                time.sleep(0.8)
                continue
            except NoSuchElementException:
                pass

            try:
                tab = self._find_by_label(SELECTORS["tab_chats"])
                tab.click()
                time.sleep(0.5)
                return True
            except NoSuchElementException:
                logger.warning("找不到「微信」tab，可能不在微信前台")
                time.sleep(1)
        return False

    def _tap_back(self) -> None:
        try:
            self.driver.find_element(
                AppiumBy.IOS_CLASS_CHAIN,
                '**/XCUIElementTypeNavigationBar/**/XCUIElementTypeButton[1]',
            ).click()
        except NoSuchElementException:
            # 退回到边缘滑动返回
            size = self.driver.get_window_size()
            self.driver.swipe(5, size["height"] // 2, size["width"] // 2, size["height"] // 2, 300)

    def list_unread_chats(self, limit: int = 5) -> list[ChatPreview]:
        """扫会话列表，挑出有未读徽标的会话。"""
        previews: list[ChatPreview] = []
        try:
            cells = self.driver.find_elements(
                AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeCell"
            )
        except WebDriverException as exc:
            logger.error("读取会话列表失败: %s", exc)
            return previews

        for cell in cells:
            try:
                labels = [
                    e.get_attribute("label") or ""
                    for e in cell.find_elements(
                        AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeStaticText"
                    )
                ]
            except WebDriverException:
                continue

            badge = next((l for l in labels if UNREAD_BADGE.match(l.strip())), None)
            if not badge:
                continue

            name = next((l for l in labels if l.strip() and l != badge), "")
            if not name:
                continue

            unread = 99 if "+" in badge else int(badge)
            previews.append(ChatPreview(name=name.strip(), unread=unread, element=cell))
            if len(previews) >= limit:
                break

        return previews

    def read_last_incoming(self) -> Optional[str]:
        """读聊天页最后一条对方发来的消息。

        判据：微信把自己发的气泡放在屏幕右半边，对方的放左半边。
        这是所有 UI 方案通用的土办法，但比猜 accessibility-id 稳。
        """
        try:
            bubbles = self.driver.find_elements(
                AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeCell/**/XCUIElementTypeStaticText"
            )
        except WebDriverException:
            return None

        width = self.driver.get_window_size()["width"]
        for element in reversed(bubbles):
            try:
                rect = element.rect
                text = (element.get_attribute("label") or "").strip()
            except WebDriverException:
                continue
            if not text:
                continue
            # 气泡中心在左半边 => 对方发的
            if rect["x"] + rect["width"] / 2 < width / 2:
                return text
        return None

    def send(self, text: str) -> bool:
        try:
            field = self.driver.find_element(
                AppiumBy.IOS_CLASS_CHAIN, "**/XCUIElementTypeTextView"
            )
        except NoSuchElementException:
            logger.error("找不到输入框，放弃发送")
            return False

        field.click()
        time.sleep(0.3)
        field.send_keys(text)
        time.sleep(0.3)

        try:
            self._find_by_label(SELECTORS["send_button"]).click()
            return True
        except NoSuchElementException:
            # 部分键盘布局下「发送」是回车键
            try:
                self.driver.execute_script("mobile: performIoHidEvent", {"page": 0x07, "usage": 0x28, "durationSeconds": 0.05})
                return True
            except WebDriverException as exc:
                logger.error("发送失败: %s", exc)
                return False

    # ------------------------------------------------------------- 主循环

    def tick(self) -> None:
        if not self.ensure_chat_list():
            return

        for preview in self.list_unread_chats():
            logger.info("发现未读会话: %s (%d 条)", preview.name, preview.unread)
            try:
                preview.element.click()
            except WebDriverException as exc:
                logger.warning("打开会话失败: %s", exc)
                continue
            time.sleep(1.2)

            text = self.read_last_incoming()
            if not text:
                logger.info("  没读到文本消息（可能是图片/语音），跳过")
                self._tap_back()
                time.sleep(0.8)
                continue

            logger.info("  最后一条: %s", text)

            # 群聊判定：微信群标题通常带成员数，如「项目组(8)」
            is_group = bool(re.search(r"\(\d+\)$", preview.name))
            mentioned = "@" in text

            decision = self.engine.decide(
                chat_name=re.sub(r"\(\d+\)$", "", preview.name),
                text=text,
                is_group=is_group,
                mentioned_me=mentioned,
            )

            if decision and decision["should_reply"]:
                reply_text = decision["text"]
                delay = decision.get("delay_seconds", 0)
                if self.dry_run:
                    logger.info("  [DRY-RUN] 本应回复: %s（延迟 %.1fs）", reply_text, delay)
                else:
                    logger.info("  等待 %.1fs 后回复: %s", delay, reply_text)
                    time.sleep(delay)
                    if self.send(reply_text):
                        logger.info("  已发送")
            else:
                reason = decision["reason"] if decision else "规则服务不可用"
                logger.info("  不回复：%s", reason)

            self._tap_back()
            time.sleep(1.0)


def build_driver(udid: str, wda_url: str) -> webdriver.Remote:
    options = XCUITestOptions()
    options.udid = udid
    options.bundle_id = WECHAT_BUNDLE_ID
    # 关键：不要让 Appium 重装或重启微信，否则会掉登录态
    options.no_reset = True
    options.set_capability("newCommandTimeout", 600)
    options.set_capability("wdaLaunchTimeout", 120_000)
    options.set_capability("shouldTerminateApp", False)
    return webdriver.Remote(wda_url, options=options)


def main() -> int:
    parser = argparse.ArgumentParser(description="iOS 微信自动回复（Appium 方案）")
    parser.add_argument("--interval", type=float, default=20.0, help="轮询间隔秒数")
    parser.add_argument("--dry-run", action="store_true", help="只打印不发送")
    parser.add_argument("--appium", default="http://127.0.0.1:4723", help="Appium server 地址")
    args = parser.parse_args()

    udid = os.environ.get("IOS_UDID", "")
    server = os.environ.get("WXAUTO_SERVER", "http://127.0.0.1:8848")
    token = os.environ.get("WXAUTO_TOKEN", "")

    if not udid:
        logger.error("请设置 IOS_UDID（用 `idevice_id -l` 或 Xcode 查看）")
        return 1
    if not token:
        logger.error("请设置 WXAUTO_TOKEN，与规则服务保持一致")
        return 1

    engine = EngineClient(server, token, os.environ.get("WXAUTO_ACCOUNT", ""))

    try:
        driver = build_driver(udid, args.appium)
    except WebDriverException as exc:
        logger.error("连接设备失败，检查 Appium / WebDriverAgent 是否就绪: %s", exc)
        return 1

    bot = WeChatIOSBot(driver, engine, dry_run=args.dry_run)
    logger.info("启动完成，每 %.0fs 扫一次%s", args.interval, "（DRY-RUN）" if args.dry_run else "")

    try:
        while True:
            try:
                bot.tick()
            except WebDriverException as exc:
                # 手机锁屏、微信被切走、WDA 断连都会走到这里，不该整个退出
                logger.warning("本轮异常，%.0fs 后重试: %s", args.interval, exc)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("收到中断，退出")
    finally:
        driver.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
