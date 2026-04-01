from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

# ── Block 类型（统一 dataclass，禁止与 dict 混用）─────────

@dataclass
class TextBlock:
    text: str

@dataclass
class ToolUseBlock:
    id: str      # 模型生成，格式如 "toolu_01abc"
    name: str    # 精确匹配 ToolSpec.name
    input: dict  # 已解析 JSON，符合 ToolSpec.input_schema

@dataclass
class ToolResultBlock:
    tool_use_id: str   # 对应 ToolUseBlock.id
    content: str       # 工具输出（失败时为错误信息）
    is_error: bool = False

# content 类型别名
ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock

@dataclass
class Message:
    role: Literal["user", "assistant"]
    # str：纯文本消息（初始 user prompt 等）
    # list：含工具调用 / 结果的结构化消息
    content: str | list[ContentBlock]

# ── 工具协议 ──────────────────────────────────────────────

RiskLevel = Literal["READ", "WRITE", "EXECUTE", "NETWORK", "STATE", "AGENT"]

@dataclass
class ToolSpec:
    name: str
    description: str    # 注入 system prompt
    input_schema: dict  # JSON Schema
    risk_level: RiskLevel
    handler: object     # Callable[[dict], dict]，返回 {"content": str, "is_error": bool}
    timeout_seconds: int = 30

# ── 权限 ──────────────────────────────────────────────────

@dataclass
class PermissionPolicy:
    allow_patterns: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)
    # headless_mode=True：跳过交互式 stdin 确认，用于 CI / 无人值守
    # 注意：deny_patterns 在 headless_mode 下仍然强制生效
    headless_mode: bool = False
    auto_approve_readonly: bool = True

# ── 运行上下文 ────────────────────────────────────────────

@dataclass
class AgentRun:
    run_id: str
    messages: list[Message]
    system_prompt: str          # 已组装，loop 启动后不可变
    tools: dict[str, ToolSpec]
    policy: PermissionPolicy
    cwd: str
    model: str = "claude-opus-4-6"
    max_iterations: int = 50