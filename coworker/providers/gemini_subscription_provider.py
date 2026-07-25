"""Gemini CLI provider for a locally cached Google AI subscription login.

The adapter stays behind the official ``gemini`` executable.  It never reads
Gemini CLI's OAuth credential file; a no-request CLI command checks whether the
official runtime can authenticate with Google, and model turns are delegated to
the same runtime in an empty temporary workspace.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .base import AssistantTurn, ModelCapabilities, ProviderClient
from .capabilities import capabilities_for
from .codex_subscription_provider import _build_prompt, _parse_tool_calls
from .local_cli import local_cli_env

_GOOGLE_AUTH_SETTINGS = {
    "security": {
        "auth": {
            "selectedType": "oauth-personal",
            "enforcedType": "oauth-personal",
        }
    }
}
_NON_SUBSCRIPTION_ENV_VARS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_ACCESS_TOKEN",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GEMINI_CLI_USE_COMPUTE_ADC",
)


def _resolve_candidate(raw: str) -> Optional[str]:
    value = (raw or "").strip()
    if not value:
        return None
    expanded = os.path.expanduser(value)
    if os.path.isabs(expanded) or os.sep in expanded:
        return expanded if os.path.isfile(expanded) else None
    return shutil.which(value)


def resolve_gemini_bin(configured: Optional[str] = None) -> Optional[str]:
    """Find Gemini CLI without hiding an invalid explicitly configured path."""
    if (configured or "").strip():
        return _resolve_candidate(configured or "")
    env_bin = _resolve_candidate(os.environ.get("GEMINI_BIN", ""))
    return env_bin or shutil.which("gemini")


def write_google_auth_settings(path: Path) -> Path:
    """Write non-secret CLI policy that pins this subprocess to Google OAuth."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_GOOGLE_AUTH_SETTINGS), encoding="utf-8")
    return path


def subscription_env(
    settings_path: Path,
    *,
    no_browser: bool = False,
    executable: Optional[str] = None,
) -> dict[str, str]:
    env = os.environ.copy()
    for key in _NON_SUBSCRIPTION_ENV_VARS:
        env.pop(key, None)
    env["GOOGLE_GENAI_USE_GCA"] = "true"
    env["GEMINI_DEFAULT_AUTH_TYPE"] = "oauth-personal"
    env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(settings_path)
    if no_browser:
        env["NO_BROWSER"] = "true"
    else:
        env.pop("NO_BROWSER", None)
    return local_cli_env(executable, env)


def _oauth_credentials_path() -> Path:
    """Return the official CLI cache location without opening or parsing it."""
    return Path.home() / ".gemini" / "oauth_creds.json"


def verify_gemini_subscription(
    gemini_bin: Optional[str] = None,
    *,
    timeout: float = 15.0,
    settings_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Detect the official OAuth cache without reading credentials or spending quota."""
    del timeout, settings_path
    explicit = (gemini_bin or "").strip()
    resolved = resolve_gemini_bin(explicit)
    if explicit and not resolved:
        return {"ok": False, "error": f"Couldn't find Gemini CLI at {explicit}."}
    if not resolved:
        return {
            "ok": False,
            "error": "Gemini CLI isn't installed. Install it and sign in with Google first.",
        }

    if _oauth_credentials_path().is_file():
        return {"ok": True, "gemini_bin": resolved, "auth_method": "google"}
    return {
        "ok": False,
        "error": "Gemini CLI is installed but not signed in with Google.",
    }


def _json_payload(raw: str) -> dict[str, Any]:
    outer = json.loads(raw)
    response = outer.get("response") if isinstance(outer, dict) else None
    if not isinstance(response, str):
        raise RuntimeError("Gemini CLI returned an invalid response envelope.")
    candidate = response.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini CLI returned invalid structured output.")
    return payload


class GeminiSubscriptionProvider(ProviderClient):
    def __init__(self, *, gemini_bin: Optional[str] = None):
        self._gemini_bin = (gemini_bin or "").strip() or None

    def _ensure_gemini(self) -> str:
        status = verify_gemini_subscription(self._gemini_bin)
        if not status.get("ok"):
            raise RuntimeError(status.get("error") or "Gemini CLI isn't ready.")
        return str(status["gemini_bin"])

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        **settings: Any,
    ) -> AssistantTurn:
        gemini_bin = self._ensure_gemini()
        timeout = float(settings.get("timeout") or 120.0)
        prompt = _build_prompt(messages, tools, runtime_name="Gemini CLI")

        with tempfile.TemporaryDirectory(prefix="coworker-gemini-") as tmp:
            policy = write_google_auth_settings(Path(tmp) / "settings.json")
            cmd = [
                gemini_bin,
                "-p",
                prompt,
                "--output-format",
                "json",
                "--approval-mode",
                "plan",
            ]
            if model and model != "default":
                cmd.extend(["--model", model])
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tmp,
                    env=subscription_env(
                        policy, no_browser=True, executable=gemini_bin
                    ),
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Gemini CLI timed out while answering.") from exc
            except Exception as exc:
                raise RuntimeError(
                    f"Couldn't start Gemini CLI ({exc.__class__.__name__})."
                ) from exc

            if proc.returncode != 0:
                detail = (
                    (proc.stderr or proc.stdout or "").strip().splitlines()[-1:]
                    or ["unknown Gemini CLI failure"]
                )[0]
                raise RuntimeError(f"Gemini CLI failed: {detail}")
            payload = _json_payload(proc.stdout)

        text = payload.get("text") or None
        tool_calls = _parse_tool_calls(payload.get("tool_calls") or [], tools)
        return AssistantTurn(
            text=text,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            raw=payload,
        )

    def capabilities(self, model: str) -> ModelCapabilities:
        routed = (
            model
            if model.startswith("gemini_subscription:")
            else f"gemini_subscription:{model}"
        )
        return capabilities_for(routed)
