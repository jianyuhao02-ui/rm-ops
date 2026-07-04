"""
AI 智能助手 Chat API
SSE 流式输出 + Function Calling + 会话记忆 + Rate Limiting
"""
import json
import time
import re
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from backend.dependencies import get_current_user
from backend.services.llm_client import get_llm_client
from backend.services.ai_tools import get_tool_definitions, execute_tool

# 过滤掉 Python JSON 无法编码的 lone surrogate 字符
_SURROGATE_RE = re.compile(r'[\ud800-\udfff]')

# DeepSeek DSML 标记清理（防御性兜底）
_DSML_BLOCK_RE = re.compile(r'<\|\s*\|\s*DSML\s*\|\|[^|]*(?:\|[^>])*\|>', re.DOTALL)


def _strip_dsml(text: str) -> str:
    """清理 DSML 标记，防止残留输出到前端"""
    text = _DSML_BLOCK_RE.sub('', text)
    # 清理单独的 <| | DSML || 开头片段（不完整标记）
    text = re.sub(r'<\|\s*\|\s*DSML[^>]*$', '', text)
    return text


def _clean_value(obj):
    """递归清理字符串中的 surrogate 字符"""
    if isinstance(obj, str):
        return _SURROGATE_RE.sub('\ufffd', obj)
    if isinstance(obj, list):
        return [_clean_value(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _clean_value(v) for k, v in obj.items()}
    return obj


def safe_json(data: dict, ensure_ascii: bool = False) -> str:
    """安全的 JSON 序列化，过滤 surrogate 字符"""
    cleaned = _clean_value(data)
    return json.dumps(cleaned, ensure_ascii=ensure_ascii)
from backend.logger import app_logger

router = APIRouter()

# ──── Request Model ────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "default"
    clear: Optional[bool] = False


class RenameRequest(BaseModel):
    name: str

# ──── 会话存储（内存 LRU） ────

MAX_SESSIONS = 200
MAX_HISTORY = 20

_sessions: dict[str, list] = {}
_session_meta: dict[str, dict] = {}  # { session_id: { name, last_message, user_id, created_at, updated_at } }
_user_sessions: dict[str, list[str]] = {}  # { user_id: [session_id, ...] }

# ──── Rate Limiting ────

_rate_limit_buckets: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_MAX = 30
RATE_WINDOW = 60


def _check_rate_limit(user_id: str) -> None:
    now = time.time()
    bucket = _rate_limit_buckets[user_id]
    bucket[:] = [t for t in bucket if now - t < RATE_WINDOW]
    if len(bucket) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    bucket.append(now)


def _cleanup_sessions():
    if len(_sessions) > MAX_SESSIONS:
        oldest = sorted(_sessions.keys())[:len(_sessions) - MAX_SESSIONS]
        for k in oldest:
            del _sessions[k]


# ──── 系统提示词 ────

SYSTEM_PROMPT = """你是三星事业部运营管理平台的 AI 智能助手。

## 当前情况
系统检测到用户提问涉及业务数据，已为你配置了数据库查询工具。你必须使用工具获取数据，严禁凭空编造。

## 工具速查
- query_sales → 销售数据、门店排名、完成率、达成情况
- query_inventory → 库存、预警、库龄、在库明细
- query_prices → 竞品价格对比、异常检测
- query_members → 会员统计、待跟进、新增
- search_kb → 知识库搜索（产品、政策、话术）
- get_insight → 经营分析洞察
- commission_query → 店员提成排名、汇总
- task_query → 任务待办、逾期、统计
- attendance_query → 考勤打卡、异常
- approval_query → 审批查询、统计
- member_detail → 会员档案、消费记录

## 回答格式
- 拿到工具返回的数据后，用Markdown表格展示
- 中文回答，专业亲切
- 不要提及工具名称

## 当前时间
{current_time}
"""


def _build_system_prompt() -> str:
    from datetime import datetime
    sp = SYSTEM_PROMPT.format(current_time=datetime.now().strftime("%Y年%m月%d日 %H:%M"))
    app_logger.info(f"[AI_DEBUG] System prompt (first 200): {sp[:200]}")
    return sp


def _get_or_create_session(session_id: str, user_id: str, clear: bool = False) -> list:
    if clear or session_id not in _sessions:
        _sessions[session_id] = [{"role": "system", "content": _build_system_prompt()}]
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        _session_meta[session_id] = {
            "name": "新对话",
            "last_message": "",
            "user_id": str(user_id),
            "created_at": now,
            "updated_at": now,
        }
        if str(user_id) not in _user_sessions:
            _user_sessions[str(user_id)] = []
        if session_id not in _user_sessions[str(user_id)]:
            _user_sessions[str(user_id)].append(session_id)
        _cleanup_sessions()
    else:
        _sessions[session_id][0] = {"role": "system", "content": _build_system_prompt()}
    return _sessions[session_id]


# ──── 会话管理端点 ────

@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """列出当前用户的所有会话"""
    uid = str(user.get("user_id", "anon"))
    session_ids = _user_sessions.get(uid, [])
    result = []
    for sid in session_ids:
        if sid in _session_meta:
            meta = _session_meta[sid]
            result.append({
                "id": sid,
                "name": meta.get("name", "新对话"),
                "last_message": meta.get("last_message", ""),
                "created_at": meta.get("created_at", ""),
                "updated_at": meta.get("updated_at", ""),
                "message_count": max(0, len(_sessions.get(sid, [])) - 1),  # 减掉 system prompt
            })
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"sessions": result}


@router.post("/session/new")
async def create_session(user: dict = Depends(get_current_user)):
    """创建新会话"""
    import uuid
    sid = f"chat_{uuid.uuid4().hex[:12]}"
    uid = str(user.get("user_id", "anon"))
    _sessions[sid] = [{"role": "system", "content": _build_system_prompt()}]
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    _session_meta[sid] = {
        "name": "新对话",
        "last_message": "",
        "user_id": uid,
        "created_at": now,
        "updated_at": now,
    }
    if uid not in _user_sessions:
        _user_sessions[uid] = []
    _user_sessions[uid].append(sid)
    return {"id": sid, "name": "新对话", "created_at": now}


@router.get("/session/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    """获取指定会话的消息列表（不含 system prompt）"""
    if session_id not in _sessions:
        return {"messages": []}
    msgs = _sessions[session_id][1:]  # 去掉 system prompt
    # 只返回 user/assistant 消息，过滤 tool 相关
    result = []
    for m in msgs:
        role = m.get("role", "")
        if role in ("user", "assistant"):
            content = m.get("content", "")
            if content:
                result.append({"role": role, "content": content})
    return {"messages": result}


@router.put("/session/{session_id}/rename")
async def rename_session(session_id: str, body: RenameRequest, user: dict = Depends(get_current_user)):
    """重命名会话"""
    if session_id in _session_meta:
        _session_meta[session_id]["name"] = body.name
    return {"status": "ok"}


# ──── 诊断端点 ────

@router.get("/status")
async def ai_status(user: dict = Depends(get_current_user)):
    """AI 助手状态诊断"""
    from backend.config import AI_API_KEY, AI_MODEL, AI_BASE_URL
    llm = get_llm_client()
    return {
        "ai_configured": bool(AI_API_KEY) and AI_API_KEY.startswith("sk-"),
        "model": AI_MODEL,
        "base_url": AI_BASE_URL,
        "demo_mode": llm._demo_mode,
        "api_key_len": len(AI_API_KEY),
        "api_key_prefix": AI_API_KEY[:15] + "..." if AI_API_KEY else "(empty)",
    }


# ──── 主端点 ────

@router.post("")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    _check_rate_limit(str(user.get("user_id", "anon")))

    user_display = user.get("display_name", "未知用户")
    user_store = user.get("store_name", "")
    user_role = user.get("role", "")

    messages = _get_or_create_session(req.session_id, str(user.get("user_id", "anon")), req.clear)

    # 自动命名：如果是新对话且有第一条用户消息
    if req.session_id in _session_meta and _session_meta[req.session_id]["name"] == "新对话":
        name = req.message[:24].strip().replace("\n", " ")
        if len(req.message) > 24:
            name += "…"
        _session_meta[req.session_id]["name"] = name

    # 构建带用户上下文的消息（不含数据泄露，仅标记身份）
    context_msg = f"[用户: {user_display} | 角色: {user_role}"
    if user_store:
        context_msg += f" | 门店: {user_store}"
    context_msg += "]"

    messages.append({"role": "user", "content": _clean_value(f"{context_msg} {req.message}")})

    if len(messages) > MAX_HISTORY * 2 + 1:
        messages[1:len(messages) - MAX_HISTORY * 2] = [
            {"role": "assistant", "content": "[对话历史已截断]"}
        ]

    tools = get_tool_definitions()
    llm = get_llm_client()

    # ── 智能路由：检测是否为业务数据查询 ──
    BUSINESS_KEYWORDS = [
        "销售", "排名", "完成率", "目标", "达成", "业绩", "卖", "销量", "趋势",
        "库存", "预警", "在库", "库龄", "缺货", "超量",
        "价格", "京东", "九机", "竞品", "低价", "降价",
        "会员", "跟进", "客户", "消费", "回访", "意向",
        "提成", "佣金", "店员", "导购", "工资",
        "任务", "待办", "todo", "逾期",
        "打卡", "考勤", "出勤", "迟到", "请假",
        "审批", "报销", "申请",
        "知识", "政策", "培训", "话术", "以旧换新",
        "分析", "洞察", "建议", "报表", "数据", "统计",
        "排名", "汇总", "对比", "明细",
    ]
    user_msg_lower = req.message.lower()
    is_data_query = any(kw in user_msg_lower for kw in BUSINESS_KEYWORDS)
    use_tools = tools if is_data_query else None
    app_logger.info(f"[AI_ROUTE] is_data_query={is_data_query}, msg_len={len(req.message)}, has_ranking={'排名' in req.message}, first_20={repr(req.message[:20])}")

    async def event_generator():
        try:
            assistant_content = ""
            _tool_buffer = ""
            _in_tool = False

            # ── 第一轮：流式调用 LLM ───
            async for chunk in llm.chat_stream(messages, use_tools):
                if _in_tool:
                    _tool_buffer += chunk
                    continue

                marker = "\n__TOOL_CALLS__\n"
                if marker in chunk and not _in_tool:
                    idx = chunk.index(marker)
                    before = chunk[:idx]
                    if before:
                        assistant_content += before
                        yield f"data: {safe_json({'type': 'text', 'content': before}, ensure_ascii=False)}\n\n"
                    _in_tool = True
                    _tool_buffer = chunk[idx + len(marker):]
                    continue

                assistant_content += chunk
                yield f"data: {safe_json({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # ── 解析工具调用 ───
            tool_calls_data = None
            if _tool_buffer:
                try:
                    tool_calls_data = json.loads(_tool_buffer)
                except json.JSONDecodeError as e:
                    app_logger.warning(f"Tool calls JSON 解析失败: {e}, raw: {_tool_buffer[:300]}")

            # ── 执行工具并二次调用 ───
            if tool_calls_data:
                for tc in tool_calls_data:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        fn_args = {}

                    tool_result = await execute_tool(fn_name, fn_args, user)
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": fn_name, "arguments": _clean_value(tc["function"]["arguments"])}
                        }]
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _clean_value(tool_result)
                    })

                # 基于工具结果生成回答（流式）
                _tool_buffer = ""
                _in_tool = False
                assistant_content = ""

                async for chunk in llm.chat_stream(messages, None):
                    if _in_tool:
                        _tool_buffer += chunk
                        continue
                    marker = "\n__TOOL_CALLS__\n"
                    if marker in chunk and not _in_tool:
                        idx = chunk.index(marker)
                        before = chunk[:idx]
                        if before:
                            assistant_content += before
                            yield f"data: {safe_json({'type': 'text', 'content': before}, ensure_ascii=False)}\n\n"
                        _in_tool = True
                        _tool_buffer = chunk[idx + len(marker):]
                        continue
                    assistant_content += chunk
                    yield f"data: {safe_json({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

            # ── 保存会话历史 ───
            assistant_content = _strip_dsml(assistant_content)
            messages.append({"role": "assistant", "content": _clean_value(assistant_content)})

            # 更新会话元数据
            if req.session_id in _session_meta:
                _session_meta[req.session_id]["last_message"] = assistant_content[:100] if assistant_content else ""
                _session_meta[req.session_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            yield f"data: {safe_json({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            app_logger.error(f"AI Chat error: {e}", exc_info=True)
            error_msg = f"抱歉，AI 服务遇到了一些问题：{str(e)[:200]}。请稍后重试或联系管理员。"
            yield f"data: {safe_json({'type': 'error', 'content': error_msg}, ensure_ascii=False)}\n\n"
            yield f"data: {safe_json({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.delete("/session/{session_id}")
async def clear_session(session_id: str, user: dict = Depends(get_current_user)):
    if session_id in _sessions:
        del _sessions[session_id]
    return {"status": "ok", "message": "会话已清除"}
