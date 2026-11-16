"""Runs one agent as a headless `claude -p` subprocess, authenticated by the user's Claude Code login."""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AgentError(RuntimeError):
    """An agent run failed: CLI missing, non-zero exit, timeout, or an error result."""


class UsageLimitError(AgentError):
    """The Claude subscription usage limit was hit; every further call will fail until it resets."""


USAGE_LIMIT_PATTERN = re.compile(r"hit your .*limit|usage limit", re.IGNORECASE)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    system_prompt: str
    model: str
    tools: tuple[str, ...] = ()
    json_schema: dict[str, Any] | None = None
    max_budget_usd: float = 1.0


@dataclass(frozen=True)
class AgentResult:
    text: str
    structured: dict[str, Any] | None
    cost_usd: float


def build_command(spec: AgentSpec, claude_path: str) -> list[str]:
    tool_list = ",".join(spec.tools)
    command = [
        claude_path,
        "-p",
        "--output-format",
        "json",
        "--no-session-persistence",
        "--setting-sources",
        "",
        # Without these, the user's MCP connectors and skill list load into every agent (~150k tokens).
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--model",
        spec.model,
        "--system-prompt",
        spec.system_prompt,
        "--max-budget-usd",
        str(spec.max_budget_usd),
        "--tools",
        tool_list,
    ]
    if spec.tools:
        command = [*command, "--allowedTools", tool_list]
    if spec.json_schema is not None:
        command = [*command, "--json-schema", json.dumps(spec.json_schema, separators=(",", ":"))]
    return command


def parse_output(stdout: str) -> AgentResult:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise AgentError(f"claude output is not valid JSON: {stdout[:300]!r}") from error
    if payload.get("is_error"):
        message = str(payload.get("result"))
        if USAGE_LIMIT_PATTERN.search(message):
            raise UsageLimitError(message[:300])
        raise AgentError(f"agent ended with {payload.get('subtype')}: {str(payload.get('result'))[:300]}")
    return AgentResult(
        text=payload.get("result") or "",
        structured=payload.get("structured_output"),
        cost_usd=float(payload.get("total_cost_usd") or 0.0),
    )


SHELL_SHIM_SUFFIXES = (".cmd", ".bat")
NPM_NATIVE_BINARY = Path("node_modules") / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"


def resolve_claude_executable() -> str:
    """Find a directly executable claude binary.

    npm installs on Windows put a `claude.cmd` shim on PATH. Running it routes every argument through
    cmd.exe, which truncates multi-line arguments and interprets & | % ^ - so we use the native binary
    the shim wraps, and refuse to run through a shim at all.
    """
    override = os.environ.get("CLAUDE_CLI_PATH")
    if override:
        return override
    found = shutil.which("claude")
    if found is None:
        raise AgentError("claude CLI not found on PATH - install Claude Code and run `claude auth login`")
    if not found.lower().endswith(SHELL_SHIM_SUFFIXES):
        return found
    native = Path(found).parent / NPM_NATIVE_BINARY
    if native.is_file():
        return str(native)
    raise AgentError(
        f"{found} is a cmd.exe shim and the native binary was not found next to it; "
        "set CLAUDE_CLI_PATH to claude.exe"
    )


def run_agent(
    spec: AgentSpec,
    prompt: str,
    *,
    sandbox_dir: Path,
    timeout_s: int,
    claude_path: str | None = None,
) -> AgentResult:
    executable = claude_path or resolve_claude_executable()
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            build_command(spec, executable),
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=sandbox_dir,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AgentError(f"{spec.name} timed out after {timeout_s}s") from error
    if completed.returncode != 0 and not completed.stdout.strip():
        raise AgentError(f"{spec.name} exited {completed.returncode}: {completed.stderr.strip()[:300]}")
    return parse_output(completed.stdout)
