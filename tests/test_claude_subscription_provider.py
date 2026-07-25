from __future__ import annotations

import json
from types import SimpleNamespace

from coworker.providers import ClaudeSubscriptionProvider
from coworker.providers.claude_subscription_provider import (
    resolve_claude_bin,
    verify_claude_subscription,
)


def test_resolve_claude_bin_explicit_path(tmp_path):
    exe = tmp_path / "claude"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    assert resolve_claude_bin(str(exe)) == str(exe)


def test_resolve_claude_bin_invalid_explicit_path_fails_closed(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/tmp/other-claude")
    assert resolve_claude_bin("/missing/claude") is None


def test_verify_accepts_first_party_subscription_and_removes_api_env(monkeypatch):
    seen = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-leak")
    monkeypatch.setattr(
        "coworker.providers.claude_subscription_provider.resolve_claude_bin",
        lambda configured=None: "/tmp/claude",
    )

    def fake_run(*args, **kwargs):
        seen["env"] = kwargs["env"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "claude.ai",
                    "apiProvider": "firstParty",
                    "subscriptionType": "max",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    result = verify_claude_subscription()
    assert result["ok"] is True
    assert result["subscription_type"] == "max"
    assert "ANTHROPIC_API_KEY" not in seen["env"]


def test_verify_rejects_non_subscription_auth(monkeypatch):
    monkeypatch.setattr(
        "coworker.providers.claude_subscription_provider.resolve_claude_bin",
        lambda configured=None: "/tmp/claude",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "api_key",
                    "apiProvider": "firstParty",
                }
            ),
            stderr="",
        ),
    )
    result = verify_claude_subscription()
    assert result["ok"] is False
    assert "subscription" in result["error"].lower()


def test_complete_disables_native_tools_and_parses_structured_output(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs["input"]
        seen["cwd"] = kwargs["cwd"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "structured_output": {"text": "hello", "tool_calls": []},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "coworker.providers.claude_subscription_provider.verify_claude_subscription",
        lambda claude_bin=None: {"ok": True, "claude_bin": "/tmp/claude"},
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    turn = ClaudeSubscriptionProvider().complete(
        model="default", messages=[{"role": "user", "content": "Say hello"}]
    )
    assert turn.text == "hello"
    assert turn.tool_calls == []
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""
    assert "--no-session-persistence" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--permission-mode") + 1] == "dontAsk"
    assert "--model" not in seen["cmd"]
    assert "Say hello" in seen["input"]
    assert "Never use shell, web, file, MCP" in seen["input"]


def test_complete_parses_openworker_tool_calls(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "structured_output": {
                        "text": "",
                        "tool_calls": [
                            {
                                "name": "read_file",
                                "arguments_json": '{"path":"notes.txt"}',
                            }
                        ],
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "coworker.providers.claude_subscription_provider.verify_claude_subscription",
        lambda claude_bin=None: {"ok": True, "claude_bin": "/tmp/claude"},
    )
    monkeypatch.setattr("subprocess.run", fake_run)
    turn = ClaudeSubscriptionProvider().complete(
        model="sonnet",
        messages=[{"role": "user", "content": "Read the file"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                },
            }
        ],
    )
    assert turn.finish_reason == "tool_calls"
    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "notes.txt"}
    assert seen["cmd"][seen["cmd"].index("--model") + 1] == "sonnet"


def test_complete_ignores_unoffered_tool_calls(monkeypatch):
    monkeypatch.setattr(
        "coworker.providers.claude_subscription_provider.verify_claude_subscription",
        lambda claude_bin=None: {"ok": True, "claude_bin": "/tmp/claude"},
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "structured_output": {
                        "text": "done",
                        "tool_calls": [
                            {"name": "read_file", "arguments_json": "{}"}
                        ],
                    }
                }
            ),
            stderr="",
        ),
    )
    turn = ClaudeSubscriptionProvider().complete(
        model="default", messages=[{"role": "user", "content": "Answer"}]
    )
    assert turn.text == "done"
    assert turn.tool_calls == []
