"""Claude Code provider that reuses a local Claude.ai subscription login.

The adapter invokes the official ``claude`` executable in non-interactive mode,
with built-in tools, MCP, project settings, and session persistence disabled. It
never reads or stores Claude OAuth credentials.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Any, Optional

from .base import AssistantTurn, ModelCapabilities, ProviderClient
from .capabilities import capabilities_for
from .codex_subscription_provider import (
    _OUTPUT_SCHEMA,
    _build_prompt,
    _parse_tool_calls,
)

_SUBSCRIPTION_AUTH = "claude.ai"
_API_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)


def _subscription_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in _API_ENV_VARS:
        env.pop(key, None)
    return env


def _resolve_candidate(raw: str) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded) or os.sep in expanded:
        return expanded if os.path.isfile(expanded) else None
    return shutil.which(value)


def resolve_claude_bin(configured: Optional[str] = None) -> Optional[str]:
    """Find Claude Code without falling back when an explicit path is invalid."""
    if (configured or "").strip():
        return _resolve_candidate(configured or "")
    env_bin = _resolve_candidate(os.environ.get("CLAUDE_BIN", ""))
    return env_bin or shutil.which("claude")


def verify_claude_subscription(
    claude_bin: Optional[str] = None, *, timeout: float = 10.0
) -> dict[str, Any]:
    """Require a first-party Claude.ai login rather than API/cloud credentials."""
    explicit = (claude_bin or "").strip()
    resolved = resolve_claude_bin(explicit)
    if explicit and not resolved:
        return {"ok": False, "error": f"Couldn't find Claude Code at {explicit}."}
    if not resolved:
        return {
            "ok": False,
            "error": "Claude Code isn't installed. Install it and sign in with Claude.ai first.",
        }

    try:
        proc = subprocess.run(
            [resolved, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_subscription_env(),
        )
    except FileNotFoundError:
        return {"ok": False, "error": "Claude Code executable is unavailable."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Claude Code login check timed out."}
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Couldn't start Claude Code ({exc.__class__.__name__}).",
        }

    output = (proc.stdout or proc.stderr or "").strip()
    try:
        status = json.loads(output)
    except json.JSONDecodeError:
        status = {}
    if (
        proc.returncode == 0
        and status.get("loggedIn") is True
        and status.get("authMethod") == _SUBSCRIPTION_AUTH
        and status.get("apiProvider") == "firstParty"
    ):
        return {
            "ok": True,
            "claude_bin": resolved,
            "subscription_type": status.get("subscriptionType") or "claude.ai",
        }
    if status.get("loggedIn") is not True:
        return {
            "ok": False,
            "error": "Claude Code is installed but not signed in. Run `claude` and sign in with Claude.ai.",
        }
    return {
        "ok": False,
        "error": "Claude Code is not using a first-party Claude.ai subscription login.",
    }


class ClaudeSubscriptionProvider(ProviderClient):
    def __init__(self, *, claude_bin: Optional[str] = None):
        self._claude_bin = (claude_bin or "").strip() or None

    def _ensure_claude(self) -> str:
        status = verify_claude_subscription(self._claude_bin)
        if not status.get("ok"):
            raise RuntimeError(status.get("error") or "Claude Code isn't ready.")
        return str(status["claude_bin"])

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ) -> AssistantTurn:
        claude_bin = self._ensure_claude()
        timeout = float(settings.get("timeout") or 120.0)
        prompt = _build_prompt(messages, tools, runtime_name="Claude Code")

        with tempfile.TemporaryDirectory(prefix="coworker-claude-") as tmp:
            cmd = [
                claude_bin,
                "-p",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(_OUTPUT_SCHEMA),
                "--tools",
                "",
                "--disable-slash-commands",
                "--no-chrome",
                "--no-session-persistence",
                "--permission-mode",
                "dontAsk",
                "--setting-sources",
                "",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--system-prompt",
                "Act only as OpenWorker's structured model adapter. Built-in tools are disabled.",
            ]
            if model and model != "default":
                cmd.extend(["--model", model])
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmp,
                    env=_subscription_env(),
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Claude Code timed out while answering.") from exc
            except Exception as exc:
                raise RuntimeError(
                    f"Couldn't start Claude Code ({exc.__class__.__name__})."
                ) from exc

            if proc.returncode != 0:
                detail = (
                    (proc.stderr or proc.stdout or "").strip().splitlines()[-1:]
                    or ["unknown Claude Code failure"]
                )[0]
                raise RuntimeError(f"Claude Code failed: {detail}")
            envelope = json.loads(proc.stdout)
            payload = envelope.get("structured_output") or {}
            if not isinstance(payload, dict):
                raise RuntimeError("Claude Code returned invalid structured output.")

        text = payload.get("text") or None
        tool_calls = _parse_tool_calls(payload.get("tool_calls") or [], tools)
        return AssistantTurn(
            text=text,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            raw=envelope,
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        routed = (
            model
            if model.startswith("claude_subscription:")
            else f"claude_subscription:{model}"
        )
        return capabilities_for(routed)
