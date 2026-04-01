from __future__ import annotations
from core.types import Message, TextBlock, ToolUseBlock, ToolResultBlock


# ── Stub（不依赖真实 API，用于 smoke test）───────────────

def _stub_response(messages: list[Message]) -> dict:
    """
    根据 messages 历史判断返回轮次。
    通过统计 user 消息中 ToolResultBlock 的数量决定：
      0 次 → 返回 tool_use (list_dir)
      ≥1 次 → 返回 end_turn
    """
    tool_result_rounds = sum(
        1 for m in messages
        if m.role == "user"
        and isinstance(m.content, list)
        and any(isinstance(b, ToolResultBlock) for b in m.content)
    )
    if tool_result_rounds == 0:
        return {
            "stop_reason": "tool_use",
            "text": "Let me check the directory.",
            "raw_tool_calls": [
                {"id": "toolu_stub_01", "name": "list_dir", "input": {"path": "."}}
            ],
        }
    else:
        return {
            "stop_reason": "end_turn",
            "text": "Done. The directory has been listed.",
            "raw_tool_calls": [],
        }


# ── 统一出口 ─────────────────────────────────────────────

def model_call(
    system: str,
    messages: list[Message],
    tools: list[dict],
    model: str,
    use_stub: bool = False,
) -> dict:
    """
    统一 model call 出口。
    返回：
    {
        "stop_reason": "end_turn" | "tool_use",
        "text": str,
        "tool_calls": list[ToolUseBlock],
    }
    """
    if use_stub:
        raw = _stub_response(messages)
        return {
            "stop_reason": raw["stop_reason"],
            "text": raw["text"],
            "tool_calls": [
                ToolUseBlock(id=tc["id"], name=tc["name"], input=tc["input"])
                for tc in raw["raw_tool_calls"]
            ],
        }

    return _call_anthropic(system, messages, tools, model)


# ── 真实 Anthropic API（use_stub=False 时调用）───────────

def _call_anthropic(
    system: str,
    messages: list[Message],
    tools: list[dict],
    model: str,
) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=8096,
        system=system,
        messages=[_serialize_message(m) for m in messages],
        tools=tools,
    )
    return _parse_response(response)


def _parse_response(response) -> dict:
    text = ""
    tool_calls: list[ToolUseBlock] = []
    for block in response.content:
        if block.type == "text":
            text = block.text
        elif block.type == "tool_use":
            tool_calls.append(ToolUseBlock(
                id=block.id,
                name=block.name,
                input=block.input,
            ))
    return {
        "stop_reason": response.stop_reason,
        "text": text,
        "tool_calls": tool_calls,
    }


def _serialize_message(msg: Message) -> dict:
    """
    把 runtime Message 序列化为 Anthropic API 格式。

    重要：role="user" 承载 ToolResultBlock 列表是 provider adapter 的兼容要求。
    Anthropic API 规定 tool_result 必须放在 user role 的 content 中。
    这不代表业务上这条消息是"用户发送的"——它是 runtime 把工具执行结果
    回传给模型的载体（tool_result carrier）。
    """
    if isinstance(msg.content, str):
        return {"role": msg.role, "content": msg.content}

    blocks = []
    for b in msg.content:
        if isinstance(b, TextBlock):
            blocks.append({"type": "text", "text": b.text})
        elif isinstance(b, ToolUseBlock):
            blocks.append({
                "type": "tool_use",
                "id": b.id,
                "name": b.name,
                "input": b.input,
            })
        elif isinstance(b, ToolResultBlock):
            # provider 适配：tool_result 放在 user role content 内
            blocks.append({
                "type": "tool_result",
                "tool_use_id": b.tool_use_id,
                "content": b.content,
                "is_error": b.is_error,
            })
    return {"role": msg.role, "content": blocks}