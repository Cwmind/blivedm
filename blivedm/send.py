import time
import asyncio
import http.cookies
import random
from typing import Optional, List

import aiohttp
import yarl  # 用于正确处理URL

import blivedm
import blivedm.models.web as web_models

# 配置区域（请根据实际情况修改）
TEST_ROOM_IDS: List[int] = [32362442]  # 直播间ID（从URL获取）

# 已登录账号的cookie（必须包含SESSDATA和bili_jct，从浏览器F12的Cookies中获取）
COOKIES = {


    "SESSDATA": "95ed59e5%2C1772958316%2C2c8ff%2A92CjCGhBSDLUWlm_9cJLO6KmB1pWorHd4yAuREIHm619Kg-W_-zO_PrxsZ8So8rp4t2gcSVjFCbnprc2xOUEN0RGhEVXVUaDR2c0tUZUpHYlAyejJSUGplcUh0WmJSZmdhZkZ6OEVTM25POGp6ZXBnNnBWdVNGLWZuOEFOdDVOcV9JU1VqMmVRWkl3IIEC",  # 例如："abcdef123456..."
    "bili_jct": "d281974263ab04becba12b3600218711"   # 即抓包中的csrf值，例如：""
}

session: Optional[aiohttp.ClientSession] = None


async def main():
    init_session()
    try:
        # 启动弹幕监听
        room_id = TEST_ROOM_IDS[0]
        client = blivedm.BLiveClient(room_id, session=session)
        handler = MyHandler()
        client.set_handler(handler)
        client.start()
        print(f"已连接直播间 {room_id}，开始监听弹幕...")

        # 测试发送弹幕（确保连接稳定后发送）
        await asyncio.sleep(2)
        await send_danmaku(room_id, "测试发送弹幕：Hello Bilibili!")

        # 持续监听120秒后退出
        await asyncio.sleep(120)
        client.stop()
        await client.join()
        print("已停止监听")
    finally:
        # 确保会话正确关闭
        if session and not session.closed:
            await session.close()
        # 等待事件循环清理资源
        await asyncio.sleep(0.2)


def init_session():
    """初始化会话并正确配置Cookie"""
    global session
    session = aiohttp.ClientSession()

    # 手动配置Cookie，确保域名正确（关键解决登录问题）
    for key, value in COOKIES.items():
        cookie = http.cookies.SimpleCookie()
        cookie[key] = value
        # 设置Cookie适用的域名（B站全域名共享）
        cookie[key]['domain'] = '.bilibili.com'
        cookie[key]['path'] = '/'
        # 将Cookie添加到会话
        session.cookie_jar.update_cookies(
            cookie,
            response_url=yarl.URL("https://www.bilibili.com")  # 基准URL
        )

    # 调试：打印已加载的Cookie
    print("已加载的Cookie：")
    for cookie in session.cookie_jar:
        print(f"{cookie.key}={cookie.value}（域名：{cookie['domain']}）")


async def send_danmaku(room_id: int, msg: str):
    """发送弹幕核心函数"""
    # 验证必要参数
    if not all(COOKIES.values()):
        print("错误：请先填写COOKIES中的SESSDATA和bili_jct")
        return

    # 获取csrf_token（即bili_jct）
    csrf_token = COOKIES["bili_jct"]

    # 生成动态参数
    current_ts = int(time.time())
    rnd = current_ts - random.randint(60, 120)  # 随机时间戳（小于当前时间）

    # 构造请求参数
    query_params = {
        "web_location": "444.8",
        "w_rid": "bd2e6f8376fa2c3165356ea010a44f21",  # 若失效需重新抓包获取
        "wts": current_ts
    }

    form_data = {
        "bubble": "0",
        "msg": msg,
        "color": "16777215",  # 白色
        "mode": "1",  # 滚动弹幕
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

    # 构造请求头（模拟浏览器环境）
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        "Referer": f"https://live.bilibili.com/{room_id}",
        "Origin": "https://live.bilibili.com",
        # 手动携带Cookie（兜底方案）
        "Cookie": f"SESSDATA={COOKIES['SESSDATA']}; bili_jct={csrf_token}"
    }

    # 发送请求
    try:
        async with session.post(
                url="https://api.live.bilibili.com/msg/send",
                params=query_params,
                data=form_data,
                headers=headers
        ) as resp:
            response_text = await resp.text()
            status = resp.status
            print(f"\n发送结果：状态码={status}，响应={response_text}")

            # 解析响应判断结果
            if status == 200:
                import json
                try:
                    result = json.loads(response_text)
                    if result.get("code") == 0:
                        print(f"✅ 弹幕发送成功：{msg}")
                    else:
                        print(f"❌ 发送失败：{result.get('message', '未知错误')}")
                except json.JSONDecodeError:
                    print("❌ 响应解析失败")
            else:
                print(f"❌ 请求失败，状态码：{status}")
    except Exception as e:
        print(f"❌ 发送异常：{str(e)}")


class MyHandler(blivedm.BaseHandler):
    """弹幕接收器"""

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        """接收普通弹幕"""
        print(f"\n[{time.strftime('%H:%M:%S')}] {message.uname}：{message.msg}")

    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
        """接收礼物消息"""
        print(f"\n[{time.strftime('%H:%M:%S')}] {message.uname} 赠送 {message.gift_name} x{message.num}")

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        """接收醒目留言"""
        print(f"\n[{time.strftime('%H:%M:%S')}] 💰 {message.uname}（¥{message.price}）：{message.message}")


if __name__ == '__main__':
    # 解决Windows事件循环问题
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Event loop is closed" not in str(e):
            raise
