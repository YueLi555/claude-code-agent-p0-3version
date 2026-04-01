from __future__ import annotations
from pathlib import Path


def read_file(input: dict) -> dict:
    """
    input: {"path": str, "start_line": int (optional), "end_line": int (optional)}
    行号从 1 开始（含）。
    """
    path = Path(input["path"])
    if not path.exists():
        return {"content": f"File not found: {path}", "is_error": True}
    if not path.is_file():
        return {"content": f"Not a file: {path}", "is_error": True}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, input.get("start_line", 1) - 1)  # 转 0-indexed
        end = input.get("end_line", len(lines))
        selected = lines[start:end]
        return {"content": "\n".join(selected)}
    except Exception as e:
        return {"content": str(e), "is_error": True}


def write_file(input: dict) -> dict:
    """
    input: {"path": str, "content": str}
    父目录不存在时自动创建。
    """
    path = Path(input["path"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(input["content"], encoding="utf-8")
        return {"content": f"Written: {path}"}
    except Exception as e:
        return {"content": str(e), "is_error": True}


def list_dir(input: dict) -> dict:
    """
    input: {"path": str (optional, default ".")}
    目录在前，文件在后，各自按名称排序。
    """
    path = Path(input.get("path", "."))
    if not path.exists():
        return {"content": f"Path not found: {path}", "is_error": True}
    if not path.is_dir():
        return {"content": f"Not a directory: {path}", "is_error": True}
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = [f"{e.name}{'/' if e.is_dir() else ''}" for e in entries]
        return {"content": "\n".join(lines) if lines else "(empty directory)"}
    except Exception as e:
        return {"content": str(e), "is_error": True}