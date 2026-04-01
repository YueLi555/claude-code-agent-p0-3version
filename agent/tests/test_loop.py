from __future__ import annotations
import pytest

from core.types import (
    AgentRun, Message, PermissionPolicy, ToolSpec,
    TextBlock, ToolUseBlock, ToolResultBlock,
)
from core.loop import run_loop
from core.permission import check_permission, _approval_key, _approval_key_to_pattern
from tools.registry import ToolRegistry
from tools.files import list_dir


# ── Helpers ───────────────────────────────────────────────

def _list_dir_spec() -> ToolSpec:
    return ToolSpec(
        name="list_dir",
        description="List directory contents",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        risk_level="READ",
        handler=list_dir,
    )


def _make_run(
    registry: ToolRegistry,
    policy: PermissionPolicy,
    prompt: str = "List the current directory",
) -> AgentRun:
    return AgentRun(
        run_id="test",
        messages=[Message(role="user", content=prompt)],
        system_prompt="You are a test agent.",
        tools=registry.all(),
        policy=policy,
        cwd=".",
    )


# ── Test 1：完整 loop 流程（stub model）──────────────────

def test_single_tool_call_loop():
    """
    验证：
    1. stub model 返回 tool_use，loop 正确解析
    2. READ 工具被 auto_approve 放行（不走交互确认）
    3. list_dir 真实执行，ToolResultBlock 内容非空
    4. tool_result 以 role="user" 追加（runtime carrier，provider 适配）
    5. 第二轮 stub 返回 end_turn，loop 正常退出并返回字符串
    """
    registry = ToolRegistry()
    registry.register(_list_dir_spec())
    policy = PermissionPolicy(headless_mode=True)
    run = _make_run(registry, policy)

    result = run_loop(run, registry, use_stub=True)

    # loop 正常返回字符串
    assert isinstance(result, str)
    assert len(result) > 0

    # messages 轮次：4 条
    # [0] user(prompt) [1] assistant(tool_use) [2] user(tool_result) [3] assistant(end)
    assert len(run.messages) == 4

    # [1] assistant：包含 ToolUseBlock
    asst = run.messages[1]
    assert asst.role == "assistant"
    assert isinstance(asst.content, list)
    tool_use_blocks = [b for b in asst.content if isinstance(b, ToolUseBlock)]
    assert len(tool_use_blocks) == 1
    assert tool_use_blocks[0].name == "list_dir"

    # [2] user：tool_result carrier（provider 适配，非业务 user）
    carrier = run.messages[2]
    assert carrier.role == "user"
    assert isinstance(carrier.content, list)
    result_blocks = [b for b in carrier.content if isinstance(b, ToolResultBlock)]
    assert len(result_blocks) == 1
    rb = result_blocks[0]
    assert rb.is_error is False
    assert rb.tool_use_id == "toolu_stub_01"
    assert len(rb.content) > 0


# ── Test 2：deny pattern 在 headless_mode 下仍然生效 ─────

def test_deny_pattern_blocks_even_in_headless():
    """
    验证 deny_patterns 优先级最高，headless_mode 不能绕过。
    """
    policy = PermissionPolicy(
        deny_patterns=["bash(rm *)"],
        headless_mode=True,
    )
    allowed, reason = check_permission(
        tool_name="bash",
        tool_input={"command": "rm -rf /tmp/test"},
        risk_level="EXECUTE",
        policy=policy,
        session_approvals=set(),
    )
    assert allowed is False
    assert reason == "denied"


# ── Test 3：session approval 细粒度 key ──────────────────

def test_session_approval_key_granularity():
    """
    验证 session approval 按 command 第一个 token 粒度：
    批准 "git status" 放行 "git log"，但 key 与 "rm" 不同。
    """
    # key 生成
    assert _approval_key("bash", {"command": "git status"}) == "bash:git"
    assert _approval_key("bash", {"command": "git log --oneline"}) == "bash:git"
    assert _approval_key("bash", {"command": "rm -rf /"}) == "bash:rm"
    assert _approval_key("write_file", {"path": "/src/foo.py"}) == "write_file:/src/foo.py"

    # 永久 pattern 生成
    assert _approval_key_to_pattern("bash", {"command": "git status"}) == "bash(git *)"
    assert _approval_key_to_pattern("write_file", {"path": "/src/foo.py"}) == "write_file(/src/foo.py)"
    assert _approval_key_to_pattern("list_dir", {}) == "list_dir(*)"

    # session 放行：git log 与 git status 共享 key
    policy = PermissionPolicy(headless_mode=False)
    session_approvals = {"bash:git"}
    allowed, reason = check_permission(
        "bash", {"command": "git log"}, "EXECUTE", policy, session_approvals
    )
    assert allowed is True
    assert reason == "session"

    # rm 不在 session，key 不同
    assert "bash:rm" not in session_approvals


# ── Test 4：unknown tool 返回 is_error ───────────────────

def test_unknown_tool_returns_error():
    registry = ToolRegistry()
    registry.register(_list_dir_spec())
    result = registry.dispatch(ToolUseBlock(id="x", name="nonexistent", input={}))
    assert result.is_error is True
    assert "Unknown tool" in result.content


# ── Test 5：headless_mode 放行 EXECUTE 工具 ───────────────

def test_headless_allows_execute_when_no_deny_match():
    """
    P0 语义确认：
    headless_mode=True 且 deny/allow 均不匹配时，
    EXECUTE 工具（bash "echo hi"）应被放行，reason="headless"。

    这是当前 P0 的有意设计：headless_mode 用于 CI / 无人值守场景，
    调用方有责任通过 deny_patterns 自行设定禁令边界。
    """
    policy = PermissionPolicy(
        allow_patterns=[],
        deny_patterns=["bash(rm *)"],   # deny 不匹配 echo
        headless_mode=True,
    )
    allowed, reason = check_permission(
        tool_name="bash",
        tool_input={"command": "echo hi"},
        risk_level="EXECUTE",
        policy=policy,
        session_approvals=set(),
    )
    assert allowed is True
    assert reason == "headless"