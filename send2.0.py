import time
import asyncio
import http.cookies
import random
from typing import Optional, List
import sys

import aiohttp
import yarl

import blivedm
import blivedm.models.web as web_models

# 配置区域
TEST_ROOM_IDS: List[int] = [32362442,26518898,1709466518,6]  # 直播间ID
COOKIES = {
    "SESSDATA": "95ed59e5%2C1772958316%2C2c8ff%2A92CjCGhBSDLUWlm_9cJLO6KmB1pWorHd4yAuREIHm619Kg-W_-zO_PrxsZ8So8rp4t2gcSVjFCbnprc2xOUEN0RGhEVXVUaDR2c0tUZUpHYlAyejJSUGplcUh0WmJSZmdhZkZ6OEVTM25POGp6ZXBnNnBWdVNGLWZuOEFOdDVOcV9JU1VqMmVRWkl3IIEC",
    "bili_jct": "d281974263ab04becba12b3600218711"
}

session: Optional[aiohttp.ClientSession] = None
is_running = True  # 控制程序运行的标志


async def main():
    global is_running
    init_session()
    try:
        room_id = TEST_ROOM_IDS[0]
        client = blivedm.BLiveClient(room_id, session=session)
        handler = MyHandler()
        client.set_handler(handler)
        client.start()
        print(f"已连接直播间 {room_id}，开始持续监听弹幕...")
        print("提示：输入弹幕内容并回车发送，输入 'exit' 退出程序\n")

        # 并行运行：监听弹幕 + 循环输入发送
        await asyncio.gather(
            client.join(),  # 监听任务（持续运行）
            send_loop(room_id)  # 发送循环任务
        )
    except KeyboardInterrupt:
        print("\n用户中断程序")
    finally:
        is_running = False
        if session and not session.closed:
            await session.close()
        await asyncio.sleep(0.2)


def init_session():
    global session
    session = aiohttp.ClientSession()
    for key, value in COOKIES.items():
        cookie = http.cookies.SimpleCookie()
        cookie[key] = value
        cookie[key]['domain'] = '.bilibili.com'
        cookie[key]['path'] = '/'
        session.cookie_jar.update_cookies(
            cookie,
            response_url=yarl.URL("https://www.bilibili.com")
        )
    # 调试Cookie
    print("已加载的Cookie：")
    for cookie in session.cookie_jar:
        print(f"{cookie.key}={cookie.value}（域名：{cookie['domain']}）")


async def send_loop(room_id: int):
    """循环输入并发送弹幕：发送后延迟0.5秒再显示输入提示"""
    global is_running
    loop = asyncio.get_event_loop()

    while is_running:
        try:
            # 显示输入提示并获取内容（仅在此处显示，避免监听时频繁弹出）
            msg = await loop.run_in_executor(
                None,
                input,
            )

            if msg.strip().lower() == 'exit':
                print("准备退出程序...")
                is_running = False
                break
            if not msg.strip():
                print("弹幕内容不能为空，跳过发送")
                continue  # 空内容直接重新显示提示，不延迟

            # 发送弹幕
            await send_danmaku(room_id, msg.strip())
            # 发送后延迟0.5秒（等待监听打印完发送的弹幕）
            await asyncio.sleep(1.5)

        except Exception as e:
            print(f"输入/发送出错：{str(e)}")
            await asyncio.sleep(1)


async def send_danmaku(room_id: int, msg: str):
    """发送单条弹幕：不显示发送成功提示"""
    if not all(COOKIES.values()):
        print("错误：请先填写COOKIES")
        return

    csrf_token = COOKIES["bili_jct"]
    current_ts = int(time.time())
    rnd = current_ts - random.randint(60, 120)

    query_params = {
        "web_location": "444.8",
        "w_rid": "bd2e6f8376fa2c3165356ea010a44f21",
        "wts": current_ts
    }

    form_data = {
        "bubble": "0",
        "msg": msg,
        "color": "16777215",
        "mode": "1",
        "room_type": "0",
        "jumpfrom": "81011",
        "reply_mid": "0",
        "reply_attr": "0",
        "replay_dmid": "",
        "statistics": '{"appId":100,"platform":5}',
        "reply_type": "0",
        "reply_uname": "",
        "data_extend": '{"trackid":"-99998"}',
        "fontsize": "25",
        "rnd": str(rnd),
        "roomid": str(room_id),
        "csrf": csrf_token,
        "csrf_token": csrf_token
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        "Referer": f"https://live.bilibili.com/{room_id}",
        "Origin": "https://live.bilibili.com",
        "Cookie": f"SESSDATA={COOKIES['SESSDATA']}; bili_jct={csrf_token}"
    }

    try:
        async with session.post(
                url="https://api.live.bilibili.com/msg/send",
                params=query_params,
                data=form_data,
                headers=headers
        ) as resp:
            response_text = await resp.text()
            status = resp.status

            if status == 200:
                import json
                try:
                    result = json.loads(response_text)
                    if result.get("code") != 0:  # 只提示失败，不提示成功
                        print(f"❌ 发送失败：{result.get('message', '未知错误')}")
                except json.JSONDecodeError:
                    print("❌ 响应解析失败")
            else:
                print(f"❌ 请求失败，状态码：{status}")
    except Exception as e:
        print(f"❌ 发送异常：{str(e)}")


class MyHandler(blivedm.BaseHandler):
    """持续监听弹幕：只打印消息，不输出未知命令日志"""

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        print(f"\n[{time.strftime('%H:%M:%S')}] {message.uname}：{message.msg}")

    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
        print(f"\n[{time.strftime('%H:%M:%S')}] {message.uname} 赠送 {message.gift_name} x{message.num}")

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        print(f"\n[{time.strftime('%H:%M:%S')}] 💰 {message.uname}（¥{message.price}）：{message.message}")

    # 关键修正：确保该方法正确缩进，属于MyHandler类
    def _on_unknown_command(self, client: blivedm.BLiveClient, cmd: str, command: dict):
        # 覆盖父类方法，不输出任何内容
        pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" not in str(e):
            raise
    print("程序已退出")