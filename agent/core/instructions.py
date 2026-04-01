from __future__ import annotations
from pathlib import Path

# 基础 system prompt，硬编码；后期可从文件加载
BASE_SYSTEM_PROMPT = """You are an agentic coding assistant.
You have access to tools to read files, write files, and run bash commands.
Work autonomously to complete the user's task.
Use tools to gather information before making changes.
Keep changes minimal and targeted.
When a tool fails, read the error and try a different approach."""


def _load_claude_md(cwd: str) -> list[str]:
    """
    从 cwd 向上扫描所有 CLAUDE.md，再加 ~/.claude/CLAUDE.md。
    返回内容列表：用户级在前（优先级最低），越近的目录越靠后（优先级越高）。
    """
    # 向上收集，近者在前
    candidates: list[str] = []
    path = Path(cwd).resolve()
    while True:
        md = path / "CLAUDE.md"
        if md.exists():
            try:
                candidates.append(md.read_text(encoding="utf-8"))
            except Exception:
                pass
        if path.parent == path:
            break
        path = path.parent

    # 用户级优先级最低，排最前
    result: list[str] = []
    user_md = Path.home() / ".claude" / "CLAUDE.md"
    if user_md.exists():
        try:
            result.append(user_md.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 远到近追加（近者在后，优先级更高）
    result.extend(reversed(candidates))
    return result


def assemble_instructions(
    base_system: str,
    cwd: str,
    tools: dict,
    extra: str | None = None,
) -> str:
    """
    拼装最终 system prompt。
    顺序：base_system → CLAUDE.md 内容（追加）→ 工具描述 → extra
    全部追加，不覆盖。
    """
    parts = [base_system.strip()]

    for md_content in _load_claude_md(cwd):
        parts.append("\n\n---\n" + md_content.strip())

    # 工具描述注入，让模型知道有哪些工具可用
    if tools:
        tool_lines = "\n".join(
            f"- {spec.name}: {spec.description}"
            for spec in tools.values()
        )
        parts.append(f"\n\nAvailable tools:\n{tool_lines}")

    if extra:
        parts.append("\n\n" + extra.strip())

    return "\n".join(parts)