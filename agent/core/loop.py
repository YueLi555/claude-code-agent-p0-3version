from __future__ import annotations
from core.types import (
    AgentRun, Message, TextBlock, ToolUseBlock, ToolResultBlock, ContentBlock
)
from core.permission import check_permission, _approval_key, _approval_key_to_pattern
from tools.registry import ToolRegistry
from adapters.model import model_call


def _build_tool_schemas(registry: ToolRegistry) -> list[dict]:
    """把 ToolSpec 转为 Anthropic API 要求的 tools 格式。"""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
        }
        for spec in registry.all().values()
    ]


def run_loop(run: AgentRun, registry: ToolRegistry, use_stub: bool = False) -> str:
    """
    主 agentic loop。返回最终 assistant 文字输出。

    messages 结构约定：
      user(prompt)
      → assistant(TextBlock + ToolUseBlock...)
      → user(ToolResultBlock...)   ← runtime 内部 carrier，见下方注释
      → assistant(TextBlock)       ← end_turn
      → ...

    注意：role="user" 承载 ToolResultBlock 列表是 provider adapter 的兼容要求
    （Anthropic API 要求 tool_result 放在 user role 下），
    不代表业务上这条消息是"用户发送的"。
    """
    tool_schemas = _build_tool_schemas(registry)
    session_approvals: set[str] = set()

    for iteration in range(run.max_iterations):

        # ── MODEL CALL ───────────────────────────────────
        response = model_call(
            system=run.system_prompt,
            messages=run.messages,
            tools=tool_schemas,
            model=run.model,
            use_stub=use_stub,
        )

        # 组装 assistant message 的 content blocks
        assistant_blocks: list[ContentBlock] = []
        if response["text"]:
            assistant_blocks.append(TextBlock(text=response["text"]))
        assistant_blocks.extend(response["tool_calls"])

        run.messages.append(Message(
            role="assistant",
            content=assistant_blocks if assistant_blocks else response["text"],
        ))

        # ── STOP CHECK ───────────────────────────────────
        if response["stop_reason"] == "end_turn" or not response["tool_calls"]:
            return response["text"]

        # ── TOOL CALLS ───────────────────────────────────
        result_blocks: list[ToolResultBlock] = []
        for tool_call in response["tool_calls"]:
            result = _handle_one_tool(tool_call, run, registry, session_approvals)
            result_blocks.append(result)

        # tool_result carrier：provider 适配要求，role="user"
        # 业务语义：runtime 将工具执行结果回传给模型
        run.messages.append(Message(role="user", content=result_blocks))

    return f"[Stopped: max_iterations ({run.max_iterations}) reached]"


def _handle_one_tool(
    tool_call: ToolUseBlock,
    run: AgentRun,
    registry: ToolRegistry,
    session_approvals: set[str],
) -> ToolResultBlock:

    spec = registry.get(tool_call.name)
    if not spec:
        return ToolResultBlock(
            tool_use_id=tool_call.id,
            content=f"Unknown tool: {tool_call.name}",
            is_error=True,
        )

    # ── PERMISSION CHECK ─────────────────────────────────
    allowed, reason = check_permission(
        tool_name=tool_call.name,
        tool_input=tool_call.input,
        risk_level=spec.risk_level,
        policy=run.policy,
        session_approvals=session_approvals,
    )

    if reason == "user_s":
        # session 级批准：写入内存 session_approvals
        session_approvals.add(_approval_key(tool_call.name, tool_call.input))
    elif reason == "user_a":
        # 永久批准：写入 policy.allow_patterns，粒度与 session key 对齐
        pattern = _approval_key_to_pattern(tool_call.name, tool_call.input)
        if pattern not in run.policy.allow_patterns:
            run.policy.allow_patterns.append(pattern)

    if not allowed:
        return ToolResultBlock(
            tool_use_id=tool_call.id,
            content="Permission denied",
            is_error=True,
        )

    # ── TOOL EXECUTE ─────────────────────────────────────
    return registry.dispatch(tool_call)