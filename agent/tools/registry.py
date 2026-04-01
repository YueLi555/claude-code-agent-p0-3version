from __future__ import annotations
from core.types import ToolSpec, ToolUseBlock, ToolResultBlock


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> dict[str, ToolSpec]:
        return dict(self._tools)

    def dispatch(self, tool_call: ToolUseBlock) -> ToolResultBlock:
        """
        职责：查找工具 → 调用 handler → catch 异常 → 包装 ToolResultBlock。

        不负责 timeout（由各工具 handler 内部处理）。
        不负责 permission（由 loop 在调用 dispatch 前完成）。
        """
        spec = self._tools.get(tool_call.name)
        if not spec:
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"Unknown tool: {tool_call.name}",
                is_error=True,
            )
        try:
            result = spec.handler(tool_call.input)
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=result["content"],
                is_error=result.get("is_error", False),
            )
        except Exception as e:
            return ToolResultBlock(
                tool_use_id=tool_call.id,
                content=f"{type(e).__name__}: {e}",
                is_error=True,
            )