from __future__ import annotations
import subprocess

MAX_OUTPUT_CHARS = 50_000


def execute_bash(input: dict) -> dict:
    """
    handler 协议：接收 dict，返回 {"content": str, "is_error": bool}

    timeout 在此层通过 subprocess.run(..., timeout=) 处理，跨平台，
    不依赖外部 signal 或 threading。
    """
    command = input.get("command", "")
    cwd = input.get("cwd") or None
    timeout = input.get("timeout", 30)

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        output = proc.stdout
        if proc.stderr:
            output += f"\n[stderr]\n{proc.stderr}"
        if proc.returncode != 0:
            output += f"\n[exit code: {proc.returncode}]"

        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f"\n[truncated at {MAX_OUTPUT_CHARS} chars]"

        return {"content": output, "is_error": proc.returncode != 0}

    except subprocess.TimeoutExpired:
        return {"content": f"Command timed out after {timeout}s", "is_error": True}
    except Exception as e:
        return {"content": str(e), "is_error": True}