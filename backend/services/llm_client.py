"""
DeepSeek LLM 客户端 - OpenAI 兼容协议
支持流式输出、Function Calling、自动重试
"""
import json
import re
import time
import asyncio
import httpx
from typing import AsyncGenerator, Optional
from backend.config import (
    AI_API_KEY, AI_BASE_URL, AI_MODEL, AI_MAX_TOKENS, AI_TEMPERATURE
)

# 超时配置
CHAT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_RETRIES = 2


# ── DeepSeek DSML 标记过滤 ──
# DeepSeek 有时在 delta.content 中输出内部标记语言，格式如：
#   <| | DSML || tool_calls|> ... </| | DSML || tool_calls|>
# 这些不是有效的 OpenAI tool_calls，需要在源头过滤掉。
_DSML_START_RE = re.compile(r'<\|\s*\|\s*DSML')
_DSML_END = '|>'


class DSMLFilter:
    """流式过滤 DeepSeek DSML 标记"""

    def __init__(self):
        self._buf = ""
        self._in_dsml = False

    def feed(self, text: str) -> str:
        """喂入文本，返回过滤后的干净文本"""
        self._buf += text
        out = []
        while self._buf:
            if self._in_dsml:
                end = self._buf.find(_DSML_END)
                if end >= 0:
                    self._buf = self._buf[end + len(_DSML_END):]
                    self._in_dsml = False
                else:
                    self._buf = ""
                    break
            else:
                m = _DSML_START_RE.search(self._buf)
                if m:
                    out.append(self._buf[:m.start()])
                    self._buf = self._buf[m.start():]
                    self._in_dsml = True
                else:
                    # 防止部分 DSML 开始标记(<| 或 <| |) 被截断
                    last_lt = self._buf.rfind('<')
                    if last_lt >= 0 and len(self._buf) - last_lt < 15:
                        out.append(self._buf[:last_lt])
                        self._buf = self._buf[last_lt:]
                    else:
                        out.append(self._buf)
                        self._buf = ""
                    break
        return "".join(out)

    def flush(self) -> str:
        """清空缓冲区，DSML 残留直接丢弃"""
        if self._in_dsml:
            self._buf = ""
            self._in_dsml = False
            return ""
        r = self._buf
        self._buf = ""
        return r


class LLMClient:
    """OpenAI 兼容的 LLM 客户端，默认对接 DeepSeek"""

    def __init__(self):
        self.api_key = AI_API_KEY
        self.base_url = AI_BASE_URL.rstrip("/")
        self.model = AI_MODEL
        self.max_tokens = AI_MAX_TOKENS
        self.temperature = AI_TEMPERATURE
        self._demo_mode = not bool(AI_API_KEY) or AI_API_KEY.strip() == ""

    def set_demo_mode(self, enabled: bool):
        self._demo_mode = enabled

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            # 既然决定传工具，就用 required 确保模型一定调用
            payload["tool_choice"] = "required"
        return payload

    async def chat(
        self,
        messages: list,
        tools: Optional[list] = None,
    ) -> dict:
        """非流式调用，返回完整响应"""
        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(messages, tools, stream=False)

        for attempt in range(1 + MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
                    resp = await client.post(url, headers=self._headers(), json=payload)
                    if resp.status_code == 200:
                        return resp.json()
                    # 非 200 重试
                    if resp.status_code >= 500 and attempt < MAX_RETRIES:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise Exception(f"LLM API error {resp.status_code}: {resp.text[:300]}")
            except httpx.TimeoutException:
                if attempt < MAX_RETRIES:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise Exception("LLM API 请求超时，请稍后重试")
            except httpx.ConnectError:
                if attempt < MAX_RETRIES:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise Exception("无法连接到 AI 服务，请检查网络")

        raise Exception("LLM API 请求失败")

    async def chat_stream(
        self,
        messages: list,
        tools: Optional[list] = None,
    ) -> AsyncGenerator[str, None]:
        """流式 SSE 调用，逐 token 产出文本片段"""
        # 提取最后一条用户消息（供演示模式使用）
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = re.sub(r"^\[.*?\]\s*", "", m.get("content", ""))
                break

        # ── 演示模式：未配置 API Key 时返回示例回答 ──
        if self._demo_mode or not self.api_key or not self.api_key.startswith("sk-"):
            async for chunk in self._demo_stream(user_msg):
                yield chunk
            return

        url = f"{self.base_url}/chat/completions"
        payload = self._build_payload(messages, tools, stream=True)

        # DEBUG: log the request
        import logging
        _log = logging.getLogger("app")
        _log.info(f"[AI_DEBUG] Sending to {url}, model={self.model}, tools={len(tools or [])}, messages={len(messages)}")
        # Dump first 300 chars of system prompt and user message
        for i, m in enumerate(messages):
            _log.info(f"[AI_DEBUG] msg[{i}] role={m['role']}, content_len={len(str(m.get('content','')))}")
        if tools:
            _log.info(f"[AI_DEBUG] tool_names={[t['function']['name'] for t in tools]}")

        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            async with client.stream(
                "POST", url, headers=self._headers(), json=payload
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    err_text = body.decode()[:500]
                    if resp.status_code == 402:
                        raise Exception("DeepSeek API 余额不足，请前往 platform.deepseek.com 充值。")
                    if resp.status_code == 401:
                        raise Exception("DeepSeek API Key 无效或已过期，请检查配置。")
                    raise Exception(f"AI 服务调用失败 [{resp.status_code}]: {err_text}")

                tool_calls = {}
                dsml = DSMLFilter()  # ── DSML 过滤器 ──
                total_content = ""
                _log.info(f"[AI_DEBUG] Stream started, status={resp.status_code}")
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    delta = chunk.get("choices", [{}])[0].get("delta", {})

                    # 处理 tool_calls 增量
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls:
                                tool_calls[idx] = {"id": tc.get("id", ""), "function": {"name": "", "arguments": ""}}
                            if "id" in tc:
                                tool_calls[idx]["id"] = tc["id"]
                            if "function" in tc:
                                name = tc["function"].get("name", "")
                                if name:
                                    tool_calls[idx]["function"]["name"] = name
                                args = tc["function"].get("arguments", "")
                                if args:
                                    tool_calls[idx]["function"]["arguments"] += args
                        continue

                    # 处理 content（过滤 DSML 标记）
                    content = delta.get("content", "")
                    if content:
                        total_content += content
                        clean = dsml.feed(content)
                        if clean:
                            yield clean

                # 清空 DSML 缓冲区残留
                tail = dsml.flush()
                if tail:
                    yield tail

                # 流结束后，如果积累了 tool_calls，一次性 yield
                _log.info(f"[AI_DEBUG] Stream ended, content_len={len(total_content)}, tool_calls={len(tool_calls)}")
                if tool_calls:
                    tool_call_list = [v for k, v in sorted(tool_calls.items())]
                    # 清理 surrogate 字符后再序列化
                    def _clean(obj):
                        if isinstance(obj, str):
                            return re.sub(r'[\ud800-\udfff]', '\ufffd', obj)
                        if isinstance(obj, list):
                            return [_clean(i) for i in obj]
                        if isinstance(obj, dict):
                            return {k: _clean(v) for k, v in obj.items()}
                        return obj
                    yield "\n__TOOL_CALLS__\n" + json.dumps(_clean(tool_call_list), ensure_ascii=False)


    async def _demo_stream(self, user_msg: str) -> AsyncGenerator[str, None]:
        """演示模式：根据关键词返回模拟回答，让前端交互可完整展示"""
        user_lower = user_msg.lower()

        if any(w in user_lower for w in ["销售", "卖", "完成率", "目标"]):
            text = (
                "根据 2026 年 6 月数据：\n\n"
                "**各门店销售完成情况：**\n\n"
                "| 门店 | 目标金额 | 已完成 | 完成率 |\n"
                "|------|--------|------|------|\n"
                "| 南明旗舰店 | ¥580,000 | ¥423,600 | **73.0%** |\n"
                "| 龙湾万达店 | ¥420,000 | ¥378,000 | **90.0%** ✅ |\n"
                "| 蒙自授权店 | ¥280,000 | ¥162,400 | **58.0%** ⚠️ |\n\n"
                "**提示：** 蒙自授权店完成率偏低，建议关注并跟进。"
            )
        elif any(w in user_lower for w in ["库存", "预警", "在库", "库龄"]):
            text = (
                "当前库存预警情况：\n\n"
                "**📦 超量库存（库存天数 > 60天）：**\n"
                "- Galaxy S24 Ultra（龙湾万达）：库存天数 72 天，建议促销\n"
                "- Galaxy Z Flip5（南明旗舰店）：库存天数 68 天，建议搭售\n\n"
                "**⚠️ 低库存（库存天数 < 7天）：**\n"
                "- Galaxy S25（蒙自授权店）：库存天数 4 天，建议补货\n\n"
                "共 **3 项**库存预警需要处理。"
            )
        elif any(w in user_lower for w in ["价格", "京东", "九机", "竞品"]):
            text = (
                "最新竞品价格对比（2026-06-07）：\n\n"
                "| 型号 | 京东 | 九机 | 最低价 |\n"
                "|------|------|------|--------|\n"
                "| S25 Ultra 512GB | ¥9,299 | ¥8,999 | **¥8,999** |\n"
                "| S25+ 256GB | ¥6,999 | ¥6,799 | **¥6,799** |\n"
                "| Z Fold6 512GB | ¥12,999 | ¥12,699 | **¥12,699** |\n\n"
                "⚠️ S25 Ultra 九机比京东低 **300 元**，建议关注竞品动态。"
            )
        elif any(w in user_lower for w in ["会员", "跟进", "客户"]):
            text = (
                "会员管理概况：\n\n"
                "- **总会员数**：1,247 人\n"
                "- **本月新增**：86 人（+7.4%）\n"
                "- **待跟进会员**：23 人\n"
                "- **高意向待回访**：8 人（超过 7 天未联系）\n\n"
                "**建议：** 优先联系以下高意向会员：\n"
                "1. 张女士（S25 Ultra，3天前到店）\n"
                "2. 李先生（Z Flip6，5天前咨询价格）"
            )
        elif any(w in user_lower for w in ["分析", "建议", "洞察", "经营"]):
            text = (
                "📊 **本月经营洞察与建议：**\n\n"
                "1. **销售节奏**：本月截至今日完成率 73%，预计可达成月度目标。\n"
                "2. **门店差异**：龙湾万达店表现优异（90%），蒙自店需重点扶持。\n"
                "3. **库存健康度**：整体良好，但 S24 Ultra 库龄偏高，建议开展以旧换新活动。\n"
                "4. **价格竞争力**：我司 S25 系列定价与竞品持平，W系列优势明显。\n\n"
                "**行动建议**：\n- 对蒙自店开展 1 对 1 辅导\n- 策划 S24 Ultra 清库活动"
            )
        elif any(w in user_lower for w in ["知识", "百事通", "政策", "培训"]):
            text = (
                "在「店长百事通」中找到相关内容：\n\n"
                "**📚 三星以旧换新政策（2026版）**\n"
                "- 支持跨品牌以旧换新\n"
                "- S 系列最高抵扣 ¥1,500\n"
                "- Fold/Flip 系列最高抵扣 ¥2,000\n"
                "- 活动期限：2026.06.01 ～ 2026.08.31\n\n"
                "如需查看完整内容，请访问「店长百事通」页面。"
            )
        elif any(w in user_lower for w in ["提成", "佣金", "店员"]):
            text = (
                "📊 **店员提成概况：**\n\n"
                "| 店员 | 所属门店 | 手机销量 | 提成金额 |\n"
                "|------|---------|---------|--------|\n"
                "| 王芳 | 南明旗舰店 | 18台 | ¥3,240 |\n"
                "| 李强 | 龙湾万达店 | 15台 | ¥2,700 |\n"
                "| 张敏 | 蒙自授权店 | 12台 | ¥2,160 |\n\n"
                "**提成规则：** 手机 ¥180/台，融合产品 3%，配件 5%，以旧换新 ¥30/台"
            )
        elif any(w in user_lower for w in ["任务", "待办", "todo"]):
            text = (
                "📋 **待办任务概览：**\n\n"
                "- 🔴 **紧急**：国庆促销方案提交（截止6/10）\n"
                "- 🟡 **高优**：库存盘点确认（截止6/12）\n"
                "- 🟢 **普通**：周报提交（截止6/14）\n"
                "- 🟢 **普通**：新品培训参加（截止6/15）\n\n"
                "共 **8 项**待办，其中 **2 项**已逾期。"
            )
        elif any(w in user_lower for w in ["打卡", "考勤", "出勤"]):
            text = (
                "📅 **今日考勤概况：**\n\n"
                "- ✅ 已签到：12 人\n"
                "- ⏳ 未签到：3 人\n"
                "- ⚠️ 迟到：1 人（张敏，9:22 签到）\n"
                "- 🏠 请假：2 人\n\n"
                "本月全勤率：**91.7%**"
            )
        elif any(w in user_lower for w in ["审批", "请假", "报销"]):
            text = (
                "📝 **审批概览：**\n\n"
                "- 🔴 待审批：5 条（请假2、报销1、采购1、通用1）\n"
                "- ✅ 已通过：28 条\n"
                "- ❌ 已驳回：3 条\n\n"
                "**最近待审批：**\n"
                "1. 李明 — 年假申请（06/12-06/14）\n"
                "2. 王芳 — 差旅报销 ¥856"
            )
        else:
            text = (
                "你好！我是三星事业部 AI 助手。我可以帮你：\n\n"
                "- 📊 **查询销售数据**：「本月销售怎么样」\n"
                "- 📦 **查看库存预警**：「有哪些库存预警」\n"
                "- 💰 **对比竞品价格**：「S25 Ultra 京东和九机哪个便宜」\n"
                "- 👥 **管理会员跟进**：「有哪些会员待跟进」\n"
                "- 💡 **获取经营建议**：「给我一些经营分析建议」\n\n"
                "请直接输入你的问题～"
            )

        # 模拟打字机效果（逐块输出）
        for i in range(0, len(text), 8):
            yield text[i:i+8]
            await asyncio.sleep(0.03)


# 全局单例
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
