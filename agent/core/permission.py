from __future__ import annotations
import fnmatch


# ── Session approval key ──────────────────────────────────

def _approval_key(tool_name: str, tool_input: dict) -> str:
    """
    生成 session approval 的 key。
    粒度：tool_name + 主要参数的规范化前缀。

    bash：取命令第一个 token（子命令级粒度）
      "git status"   → "bash:git"
      "pytest tests" → "bash:pytest"
    write_file：取路径（文件级粒度）
      "/src/foo.py"  → "write_file:/src/foo.py"
    其他工具：仅 tool_name
    """
    if tool_name == "bash":
        command = tool_input.get("command", "").strip()
        tokens = command.split()
        first_token = tokens[0] if tokens else ""
        return f"bash:{first_token}"
    elif tool_name == "write_file":
        path = tool_input.get("path", "")
        return f"write_file:{path}"
    else:
        return tool_name


def _approval_key_to_pattern(tool_name: str, tool_input: dict) -> str:
    """
    把 session approval key 转换为可写入 allow_patterns 的永久 pattern。
    粒度与 _approval_key 对齐，比 tool_name(*) 更细。

    bash:git              → "bash(git *)"
    write_file:/src/foo   → "write_file(/src/foo)"
    其他                  → "tool_name(*)"
    """
    if tool_name == "bash":
        command = tool_input.get("command", "").strip()
        tokens = command.split()
        first_token = tokens[0] if tokens else ""
        if first_token:
            return f"bash({first_token} *)"
        return "bash(*)"
    elif tool_name == "write_file":
        path = tool_input.get("path", "")
        if path:
            return f"write_file({path})"
        return "write_file(*)"
    else:
        return f"{tool_name}(*)"


# ── Pattern 匹配 ──────────────────────────────────────────

def _primary_arg(tool_name: str, tool_input: dict) -> str:
    if tool_name == "bash":
        return tool_input.get("command", "")
    elif tool_name in ("read_file", "write_file"):
        return tool_input.get("path", "")
    return ""


def _matches_any(patterns: list[str], tool_name: str, tool_input: dict) -> bool:
    """
    支持格式：
      "read_file"     → 匹配工具名
      "bash(*)"       → 匹配所有 bash 调用
      "bash(git *)"   → 匹配 command 以 "git " 开头的 bash 调用
    """
    arg = _primary_arg(tool_name, tool_input)
    for pattern in patterns:
        if "(" in pattern:
            name_part, rest = pattern.split("(", 1)
            arg_pattern = rest.rstrip(")")
            if name_part == tool_name and fnmatch.fnmatch(arg, arg_pattern):
                return True
        else:
            if fnmatch.fnmatch(tool_name, pattern):
                return True
    return False


# ── 主检查函数 ────────────────────────────────────────────

def check_permission(
    tool_name: str,
    tool_input: dict,
    risk_level: str,
    policy: "PermissionPolicy",
    session_approvals: set[str],
) -> tuple[bool, str]:
    """
    返回 (allowed: bool, reason: str)

    评估顺序（严格按此顺序，不可跳过）：
      1. deny_patterns 命中 → False, "denied"
      2. allow_patterns 命中 → True,  "allow_list"
      3. headless_mode=True → True,  "headless"
      4. READ + auto_approve_readonly → True,  "readonly"
      5. session_approvals 命中 → True,  "session"
      6. 交互确认 → True/False, "user_y/s/a/n"

    reason 含义（调用方使用）：
      "denied"     → deny pattern 命中，硬拒绝
      "allow_list" → allow pattern 放行
      "headless"   → headless_mode 跳过交互，放行
      "readonly"   → READ 工具自动放行
      "session"    → session 级已批准
      "user_y"     → 用户单次确认
      "user_s"     → 用户批准本 session（调用方写入 session_approvals）
      "user_a"     → 用户永久批准（调用方写入 policy.allow_patterns）
      "user_n"     → 用户拒绝
    """
    # 1. deny 永远优先，headless_mode 不影响此规则
    if _matches_any(policy.deny_patterns, tool_name, tool_input):
        return False, "denied"

    # 2. allow list 静态放行
    if _matches_any(policy.allow_patterns, tool_name, tool_input):
        return True, "allow_list"

    # 3. headless_mode：跳过交互式确认（deny 已在步骤 1 拦截）
    if policy.headless_mode:
        return True, "headless"

    # 4. 只读自动放行
    if risk_level == "READ" and policy.auto_approve_readonly:
        return True, "readonly"

    # 5. session 级已批准（细粒度 key）
    key = _approval_key(tool_name, tool_input)
    if key in session_approvals:
        return True, "session"

    # 6. 交互确认
    return _ask_user(tool_name, tool_input)


def _ask_user(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    import json
    print(f"\n[Permission Required]")
    print(f"  Tool  : {tool_name}")
    print(f"  Input : {json.dumps(tool_input, ensure_ascii=False)[:300]}")
    print(f"  [y] Once  [s] This session  [a] Always  [n] Deny")
    while True:
        choice = input("  > ").strip().lower()
        if choice in ("y", "s", "a", "n"):
            allowed = choice != "n"
            return allowed, f"user_{choice}"
        print("  Invalid input, enter y / s / a / n")