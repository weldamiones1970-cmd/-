import aiohttp
import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import AstrBotConfig, logger

class OilPricePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    @filter.command("油价")
    async def query_oil_price(self, event: AstrMessageEvent):
        # ==================== 修正点 1：无差别提取城市名 ====================
        # 1. 获取原始消息，去掉"油价"两个字
        raw_msg = event.message_str.replace("油价", "")
        # 2. 正则提取：只保留中文字符（过滤掉空格、斜杠、@符号等所有干扰）
        city = re.sub(r'[^\u4e00-\u9fa5]', '', raw_msg)
        
        if not city:
            yield event.plain_result("请提供城市名称，例如：/油价 北京")
            return

        api_key = self.config.get("api_key", "")
        if not api_key:
            yield event.plain_result("❌ 插件未配置 API Key，请联系管理员在面板中设置。")
            return

        # ==================== 修正点 2：按官方文档只传 key ====================
        # 官方文档请求参数只有 key，所以直接拉取全国数据，然后在本地过滤
        params = {
            "key": api_key,
            "dtype": "json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://apis.juhe.cn/gnyj/query", # 你的 gnyj 是正确的
                    params=params,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10
                ) as resp:
                    if resp.status != 200:
                        yield event.plain_result(f"⚠️ 请求失败，HTTP 状态码：{resp.status}")
                        return
                    data = await resp.json()

            # 判断 error_code，彻底摆脱 "success!" 的魔咒
            if data.get("error_code") != 0:
                error_msg = data.get("reason", "未知错误")
                yield event.plain_result(f"❌ 查询失败：{error_msg}")
                return

            result_list = data.get("result", [])
            if not result_list or not isinstance(result_list, list):
                yield event.plain_result("❌ 未获取到油价数据，请稍后再试。")
                return

            target_city_data = None
            # ==================== 修正点 3：智能模糊匹配 ====================
            for item in result_list:
                api_city = item.get("city", "")
                # 只要输入的中文包含在API返回的省份里，或者反过来，就算匹配成功
                if city in api_city or api_city in city:
                    target_city_data = item
                    break

            if not target_city_data:
                yield event.plain_result(f"❌ 未查到「{city}」的油价，可能该省份不支持查询，请尝试输入省份名（如：甘肃、北京）。")
                return

            # 提取数据
            city_name = target_city_data.get("city", city)
            oil_92 = target_city_data.get("92h", "N/A")
            oil_95 = target_city_data.get("95h", "N/A")
            oil_98 = target_city_data.get("98h", "N/A")
            oil_0 = target_city_data.get("0h", "N/A")

            # 完全遵循“赛博蟹老板”的简洁输出原则
            reply_msg = (
                f"📍 {city_name} 今日油价：\n"
                f"▪ 92号汽油：{oil_92} 元/升\n"
                f"▪ 95号汽油：{oil_95} 元/升\n"
                f"▪ 98号汽油：{oil_98} 元/升\n"
                f"▪ 0号柴油：{oil_0} 元/升"
            )
            yield event.plain_result(reply_msg)

        except aiohttp.ClientError as e:
            logger.error(f"油价查询请求异常: {e}")
            yield event.plain_result("⚠️ 查询网络异常，请稍后再试。")
        except Exception as e:
            logger.error(f"油价查询未知异常: {e}")
            yield event.plain_result("⚠️ 查询时发生未知错误。")