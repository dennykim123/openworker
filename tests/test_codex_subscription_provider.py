from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from coworker.providers import CodexSubscriptionProvider
from coworker.providers.codex_subscription_provider import (
    resolve_codex_bin,
    verify_codex_subscription,
)


def test_resolve_codex_bin_explicit_path(tmp_path):
    exe = tmp_path / "codex"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    assert resolve_codex_bin(str(exe)) == str(exe)


def test_resolve_codex_bin_invalid_explicit_path_fails_closed(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/tmp/other-codex")
    assert resolve_codex_bin("/missing/codex") is None


def test_verify_codex_subscription_accepts_chatgpt_login(monkeypatch):
    monkeypatch.setattr(
        "coworker.providers.codex_subscription_provider.resolve_codex_bin",
        lambda configured=None: "/tmp/codex",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="Logged in using ChatGPT\n", stderr=""
        ),
    )
    assert verify_codex_subscription()["ok"] is True


def test_verify_codex_subscription_rejects_api_key_login(monkeypatch):
    monkeypatch.setattr(
        "coworker.providers.codex_subscription_provider.resolve_codex_bin",
        lambda configured=None: "/tmp/codex",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="Logged in using API key\n", stderr=""
        ),
    )
    res = verify_codex_subscription()
    assert res["ok"] is False
    assert "subscription" in res["error"].lower()


def test_complete_uses_output_file_and_omits_model_for_default(monkeypatch):
    seen: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["input"] = kwargs["input"]
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text(
            json.dumps({"text": "hello", "tool_calls": []}), encoding="utf-8"
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "coworker.providers.codex_subscription_provider.verify_codex_subscription",
        lambda codex_bin=None: {"ok": True, "codex_bin": "/tmp/codex"},
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    provider = CodexSubscriptionProvider()
    turn = provider.complete(
        model="default",
        messages=[{"role": "user", "content": "Say hello"}],
    )

    assert turn.text == "hello"
    assert turn.tool_calls == []
    assert "-m" not in seen["cmd"]
    assert "Say hello" in str(seen["input"])
    assert "--ephemeral" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in seen["cmd"]
    assert "--ignore-rules" in seen["cmd"]
    assert "Never use shell, web, file, MCP" in str(seen["input"])


def test_complete_parses_tool_calls(monkeypatch):
    def fake_run(cmd, **kwargs):
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text(
            json.dumps(
                {
                    "text": "",
                    "tool_calls": [
                        {
                            "name": "read_file",
                            "arguments_json": '{"path":"notes.txt"}',
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "coworker.providers.codex_subscription_provider.verify_codex_subscription",
        lambda codex_bin=None: {"ok": True, "codex_bin": "/tmp/codex"},
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    provider = CodexSubscriptionProvider()
    turn = provider.complete(
        model="gpt-5.6-sol",
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
    assert len(turn.tool_calls) == 1
    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "notes.txt"}


def test_complete_ignores_tool_calls_when_no_tools_were_offered(monkeypatch):
    def fake_run(cmd, **kwargs):
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text(
            json.dumps(
                {
                    "text": "done",
                    "tool_calls": [
                        {
                            "name": "read_file",
                            "arguments_json": '{"path":"notes.txt"}',
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "coworker.providers.codex_subscription_provider.verify_codex_subscription",
        lambda codex_bin=None: {"ok": True, "codex_bin": "/tmp/codex"},
    )
    monkeypatch.setattr("subprocess.run", fake_run)

    turn = CodexSubscriptionProvider().complete(
        model="default",
        messages=[{"role": "user", "content": "Answer directly"}],
    )

    assert turn.text == "done"
    assert turn.tool_calls == []
