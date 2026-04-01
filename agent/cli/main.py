from __future__ import annotations
import argparse
import os
import uuid

from core.types import AgentRun, Message, PermissionPolicy, ToolSpec
from core.instructions import assemble_instructions, BASE_SYSTEM_PROMPT
from core.loop import run_loop
from tools.registry import ToolRegistry
from tools.bash import execute_bash
from tools.files import read_file, write_file, list_dir


def _build_registry() -> ToolRegistry:
    r = ToolRegistry()
    r.register(ToolSpec(
        name="bash",
        description="Run a bash command in a shell. Returns stdout, stderr, and exit code.",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The bash command to run"},
                "cwd": {"type": "string", "description": "Working directory (optional)"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
            },
            "required": ["command"],
        },
        risk_level="EXECUTE",
        handler=execute_bash,
    ))
    r.register(ToolSpec(
        name="read_file",
        description="Read a file's contents, optionally limited to a line range.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["path"],
        },
        risk_level="READ",
        handler=read_file,
    ))
    r.register(ToolSpec(
        name="write_file",
        description="Write content to a file, creating parent directories if needed.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        risk_level="WRITE",
        handler=write_file,
    ))
    r.register(ToolSpec(
        name="list_dir",
        description="List the contents of a directory.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default '.')"},
            },
        },
        risk_level="READ",
        handler=list_dir,
    ))
    return r


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal agent CLI (P0)")
    parser.add_argument("--prompt", required=True, help="Task prompt for the agent")
    parser.add_argument("--model", default="claude-opus-4-6", help="Model name")
    parser.add_argument("--allow", action="append", default=[], metavar="PATTERN",
                        help="Add allow pattern, e.g. 'bash(git *)'")
    parser.add_argument("--deny", action="append", default=[], metavar="PATTERN",
                        help="Add deny pattern, e.g. 'bash(rm *)'")
    parser.add_argument("--headless", action="store_true",
                        help="Skip interactive approval (deny rules still apply)")
    parser.add_argument("--stub", action="store_true",
                        help="Use stub model response instead of real API")
    args = parser.parse_args()

    registry = _build_registry()

    deny_patterns = args.deny if args.deny else ["bash(rm -rf *)"]
    policy = PermissionPolicy(
        allow_patterns=args.allow,
        deny_patterns=deny_patterns,
        headless_mode=args.headless,
    )

    cwd = os.getcwd()
    system_prompt = assemble_instructions(BASE_SYSTEM_PROMPT, cwd, registry.all())

    run = AgentRun(
        run_id=str(uuid.uuid4())[:8],
        messages=[Message(role="user", content=args.prompt)],
        system_prompt=system_prompt,
        tools=registry.all(),
        policy=policy,
        cwd=cwd,
        model=args.model,
    )

    result = run_loop(run, registry, use_stub=args.stub)
    print(f"\n{result}")


if __name__ == "__main__":
    main()