"""Codex-backed provider that reuses the local ChatGPT subscription login.

This adapter deliberately stays on the official local Codex runtime boundary: it
invokes the installed `codex` executable in ephemeral, read-only mode and never
reads token files or imports bearer tokens into OpenWorker.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .base import AssistantTurn, ModelCapabilities, ProviderClient, ToolCall
from .capabilities import capabilities_for

_KNOWN_MACOS_BINS = [
    "/Applications/ChatGPT.app/Contents/Resources/codex",
    "~/Applications/ChatGPT.app/Contents/Resources/codex",
]
_LOGIN_OK = "logged in using chatgpt"
_LOGIN_API_KEY = "logged in using api key"
_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "tool_calls": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "arguments_json": {"type": "string"},
                },
                "required": ["name", "arguments_json"],
            },
        },
    },
    "required": ["text", "tool_calls"],
}


def _resolve_candidate(raw: str) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded) or os.sep in expanded:
        return expanded if os.path.isfile(expanded) else None
    return shutil.which(value)


def resolve_codex_bin(configured: Optional[str] = None) -> Optional[str]:
    """Best-effort discovery of the official local Codex executable."""
    if (configured or "").strip():
        # An explicit choice must fail closed instead of silently switching to a
        # different executable from PATH.
        return _resolve_candidate(configured or "")

    env_bin = _resolve_candidate(os.environ.get("CODEX_BIN", ""))
    if env_bin:
        return env_bin

    path_bin = shutil.which("codex")
    if path_bin:
        return path_bin

    for candidate in _KNOWN_MACOS_BINS:
        resolved = _resolve_candidate(candidate)
        if resolved:
            return resolved
    return None


def verify_codex_subscription(
    codex_bin: Optional[str] = None, *, timeout: float = 10.0
) -> dict[str, Any]:
    """Verify that Codex exists locally and is logged in with ChatGPT."""
    explicit = (codex_bin or "").strip()
    resolved = resolve_codex_bin(explicit)
    if explicit and not resolved:
        return {
            "ok": False,
            "error": f"Couldn't find Codex at {explicit}.",
        }
    if not resolved:
        return {
            "ok": False,
            "error": "Codex isn't installed. Install the ChatGPT desktop app or set a Codex path.",
        }

    try:
        proc = subprocess.run(
            [resolved, "login", "status"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "Codex executable is unavailable."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Codex login check timed out."}
    except Exception as exc:
        return {"ok": False, "error": f"Couldn't start Codex ({exc.__class__.__name__})."}

    output = "\n".join(x for x in [proc.stdout, proc.stderr] if x).strip()
    lowered = output.lower()
    if proc.returncode == 0 and _LOGIN_OK in lowered:
        return {"ok": True, "codex_bin": resolved}
    if _LOGIN_API_KEY in lowered:
        return {
            "ok": False,
            "error": "Codex is signed in with an API key. Sign in with ChatGPT to use your subscription.",
        }
    if "not logged in" in lowered or "login required" in lowered:
        return {
            "ok": False,
            "error": "Codex is installed but not signed in. Open ChatGPT and sign in to Codex first.",
        }
    detail = output.splitlines()[-1] if output else f"exit code {proc.returncode}"
    return {"ok": False, "error": f"Codex login check failed: {detail}"}


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if not isinstance(part, dict):
                parts.append(str(part))
                continue
            kind = part.get("type")
            if kind == "text":
                parts.append(str(part.get("text") or ""))
            elif kind == "image_url":
                parts.append("[image omitted]")
            elif kind == "file":
                parts.append("[file omitted]")
            else:
                parts.append(f"[{kind or 'non-text content'} omitted]")
        return "\n".join(x for x in parts if x).strip()
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        if role == "notice":
            continue
        item: dict[str, Any] = {"role": role, "content": _stringify_content(msg.get("content"))}
        if role == "assistant" and msg.get("tool_calls"):
            calls: list[dict[str, Any]] = []
            for tc in msg.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else tc
                raw_args = fn.get("arguments") if isinstance(fn, dict) else {}
                if isinstance(raw_args, str):
                    try:
                        arguments = json.loads(raw_args)
                    except json.JSONDecodeError:
                        arguments = {"_raw": raw_args}
                else:
                    arguments = raw_args or {}
                calls.append(
                    {
                        "id": str(tc.get("id") or ""),
                        "name": str(fn.get("name") or ""),
                        "arguments": arguments if isinstance(arguments, dict) else {"_raw": raw_args},
                    }
                )
            if calls:
                item["tool_calls"] = calls
        if role == "tool":
            if msg.get("tool_call_id"):
                item["tool_call_id"] = str(msg["tool_call_id"])
            if msg.get("name"):
                item["name"] = str(msg["name"])
        clean.append(item)
    return clean


def _tool_specs(tools: Optional[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for tool in tools or []:
        fn = (tool or {}).get("function") or {}
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        specs.append(
            {
                "name": name,
                "description": fn.get("description") or "",
                "parameters": fn.get("parameters") or {"type": "object"},
            }
        )
    return specs


def _build_prompt(messages: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]]) -> str:
    return "\n".join(
        [
            "You are a JSON adapter between OpenWorker and Codex.",
            "Never use shell, web, file, MCP, or any native Codex tools.",
            "Never modify the computer or execute the supplied tools yourself.",
            "Return only JSON matching the provided schema.",
            "When a tool is needed, emit it in tool_calls with the exact tool name and JSON-stringified arguments.",
            "If no tool is needed, answer in text and leave tool_calls empty.",
            "",
            "<tools>",
            json.dumps(_tool_specs(tools), ensure_ascii=False, indent=2),
            "</tools>",
            "",
            "<conversation>",
            json.dumps(_sanitize_messages(messages), ensure_ascii=False, indent=2),
            "</conversation>",
        ]
    )


def _parse_tool_calls(
    raw: list[dict[str, Any]], tools: Optional[list[dict[str, Any]]]
) -> list[ToolCall]:
    allowed = {spec["name"] for spec in _tool_specs(tools)}
    if not allowed:
        return []
    calls: list[ToolCall] = []
    for i, item in enumerate(raw or []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name or (allowed and name not in allowed):
            continue
        raw_args = item.get("arguments_json") or "{}"
        try:
            arguments = json.loads(raw_args)
        except (TypeError, json.JSONDecodeError):
            arguments = {"_raw": raw_args}
        if not isinstance(arguments, dict):
            arguments = {"_raw": raw_args}
        calls.append(
            ToolCall(id=f"call_codex_{i}", name=name, arguments=arguments)
        )
    return calls


class CodexSubscriptionProvider(ProviderClient):
    def __init__(self, *, codex_bin: Optional[str] = None):
        self._codex_bin = (codex_bin or "").strip() or None

    def _ensure_codex(self) -> str:
        status = verify_codex_subscription(self._codex_bin)
        if not status.get("ok"):
            raise RuntimeError(status.get("error") or "Codex isn't ready.")
        return str(status["codex_bin"])

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ) -> AssistantTurn:
        codex_bin = self._ensure_codex()
        timeout = float(settings.get("timeout") or 120.0)
        prompt = _build_prompt(messages, tools)

        with tempfile.TemporaryDirectory(prefix="coworker-codex-") as tmp:
            tmp_path = Path(tmp)
            schema_path = tmp_path / "schema.json"
            output_path = tmp_path / "last.json"
            schema_path.write_text(json.dumps(_OUTPUT_SCHEMA), encoding="utf-8")

            cmd = [
                codex_bin,
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--ignore-rules",
                "--color",
                "never",
                "--output-schema",
                str(schema_path),
                "-o",
                str(output_path),
                "-C",
                tmp,
            ]
            if model and model != "default":
                cmd.extend(["-m", model])
            cmd.append("-")
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Codex timed out while answering.") from exc
            except Exception as exc:
                raise RuntimeError(
                    f"Couldn't start Codex ({exc.__class__.__name__})."
                ) from exc

            if proc.returncode != 0:
                detail = (
                    (proc.stderr or proc.stdout or "").strip().splitlines()[-1:]
                    or ["unknown Codex failure"]
                )[0]
                raise RuntimeError(f"Codex failed: {detail}")

            payload = json.loads(output_path.read_text(encoding="utf-8"))
        text = payload.get("text") or None
        tool_calls = _parse_tool_calls(payload.get("tool_calls") or [], tools)
        return AssistantTurn(
            text=text,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            raw=payload,
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        routed = model if model.startswith("codex:") else f"codex:{model}"
        return capabilities_for(routed)
