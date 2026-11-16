import json
import subprocess

import pytest

from docreview.runner import (
    AgentError,
    AgentSpec,
    UsageLimitError,
    build_command,
    parse_output,
    resolve_claude_executable,
    run_agent,
)

CLAUDE_PATH = "C:/fake/claude.exe"


def make_spec(**overrides):
    base = {
        "name": "researcher",
        "system_prompt": "You research.",
        "model": "sonnet",
        "tools": ("WebSearch", "WebFetch"),
        "max_budget_usd": 1.5,
    }
    return AgentSpec(**{**base, **overrides})


def success_payload(**overrides):
    base = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "answer text",
        "total_cost_usd": 0.12,
    }
    return json.dumps({**base, **overrides})


def test_build_command_with_tools_restricts_and_preapproves_them():
    command = build_command(make_spec(), CLAUDE_PATH)

    assert command[0] == CLAUDE_PATH
    assert "-p" in command
    assert command[command.index("--tools") + 1] == "WebSearch,WebFetch"
    assert command[command.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert command[command.index("--model") + 1] == "sonnet"
    assert command[command.index("--system-prompt") + 1] == "You research."
    assert command[command.index("--max-budget-usd") + 1] == "1.5"
    assert command[command.index("--setting-sources") + 1] == ""
    assert "--no-session-persistence" in command


def test_build_command_without_tools_disables_all_tools():
    command = build_command(make_spec(tools=()), CLAUDE_PATH)

    assert command[command.index("--tools") + 1] == ""
    assert "--allowedTools" not in command


def test_build_command_with_schema_passes_compact_json():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    command = build_command(make_spec(json_schema=schema), CLAUDE_PATH)

    assert json.loads(command[command.index("--json-schema") + 1]) == schema


def test_build_command_without_schema_omits_flag():
    assert "--json-schema" not in build_command(make_spec(), CLAUDE_PATH)


def test_parse_output_when_success_returns_text_and_cost():
    result = parse_output(success_payload())

    assert result.text == "answer text"
    assert result.cost_usd == pytest.approx(0.12)
    assert result.structured is None


def test_parse_output_when_structured_returns_structured_dict():
    result = parse_output(success_payload(structured_output={"questions": ["a"]}))

    assert result.structured == {"questions": ["a"]}


def test_parse_output_when_is_error_raises_with_subtype():
    with pytest.raises(AgentError, match="error_max_budget_usd"):
        parse_output(success_payload(is_error=True, subtype="error_max_budget_usd"))


def test_parse_output_when_not_json_raises():
    with pytest.raises(AgentError, match="not valid JSON"):
        parse_output("Error: not logged in")


def test_parse_output_when_missing_cost_defaults_to_zero():
    payload = json.loads(success_payload())
    del payload["total_cost_usd"]

    assert parse_output(json.dumps(payload)).cost_usd == 0.0


def test_run_agent_sends_prompt_on_stdin_in_sandbox(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, success_payload(), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_agent(make_spec(), "What is X?", sandbox_dir=tmp_path, timeout_s=30, claude_path=CLAUDE_PATH)

    assert result.text == "answer text"
    assert captured["kwargs"]["input"] == "What is X?"
    assert captured["kwargs"]["cwd"] == tmp_path
    assert captured["kwargs"]["timeout"] == 30
    assert "shell" not in captured["kwargs"]


def test_run_agent_when_nonzero_exit_and_no_json_raises_with_stderr(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "boom"),
    )

    with pytest.raises(AgentError, match="boom"):
        run_agent(make_spec(), "q", sandbox_dir=tmp_path, timeout_s=5, claude_path=CLAUDE_PATH)


def test_run_agent_when_timeout_raises_agent_error(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(AgentError, match="timed out"):
        run_agent(make_spec(), "q", sandbox_dir=tmp_path, timeout_s=5, claude_path=CLAUDE_PATH)


def test_run_agent_creates_missing_sandbox_dir(monkeypatch, tmp_path):
    sandbox = tmp_path / "nested" / "sandbox"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, success_payload(), ""),
    )

    run_agent(make_spec(), "q", sandbox_dir=sandbox, timeout_s=5, claude_path=CLAUDE_PATH)

    assert sandbox.is_dir()


def test_run_agent_when_claude_not_found_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("docreview.runner.shutil.which", lambda name: None)

    with pytest.raises(AgentError, match="claude CLI not found"):
        run_agent(make_spec(), "q", sandbox_dir=tmp_path, timeout_s=5)


def test_resolve_claude_executable_when_env_override_returns_it(monkeypatch, tmp_path):
    override = tmp_path / "claude.exe"
    override.touch()
    monkeypatch.setenv("CLAUDE_CLI_PATH", str(override))

    assert resolve_claude_executable() == str(override)


def test_resolve_claude_executable_when_native_binary_on_path_returns_it(monkeypatch, tmp_path):
    native = tmp_path / "claude.exe"
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("docreview.runner.shutil.which", lambda name: str(native))

    assert resolve_claude_executable() == str(native)


def test_resolve_claude_executable_when_npm_cmd_shim_returns_wrapped_exe(monkeypatch, tmp_path):
    shim = tmp_path / "claude.CMD"
    shim.touch()
    native = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.touch()
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("docreview.runner.shutil.which", lambda name: str(shim))

    assert resolve_claude_executable() == str(native)


def test_resolve_claude_executable_when_shim_without_native_binary_refuses(monkeypatch, tmp_path):
    shim = tmp_path / "claude.cmd"
    shim.touch()
    monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)
    monkeypatch.setattr("docreview.runner.shutil.which", lambda name: str(shim))

    with pytest.raises(AgentError, match="cmd.exe"):
        resolve_claude_executable()


def test_parse_output_when_usage_limit_raises_usage_limit_error():
    payload = success_payload(
        is_error=True, result="You've hit your 5-hour limit - resets 8:20pm (Europe/Paris)"
    )

    with pytest.raises(UsageLimitError, match="resets 8:20pm"):
        parse_output(payload)


def test_usage_limit_error_is_an_agent_error():
    assert issubclass(UsageLimitError, AgentError)


def test_build_command_excludes_user_mcp_servers_and_skills():
    command = build_command(make_spec(), CLAUDE_PATH)

    assert "--strict-mcp-config" in command
    assert "--disable-slash-commands" in command
