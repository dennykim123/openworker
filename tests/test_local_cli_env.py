from __future__ import annotations

from coworker.providers.local_cli import local_cli_env


def test_local_cli_env_prepends_runtime_directory_and_preserves_path() -> None:
    env = local_cli_env(
        "/Users/example/.nvm/versions/node/v22/bin/claude",
        {"PATH": "/usr/bin:/bin", "KEEP_ME": "yes"},
    )

    entries = env["PATH"].split(":")
    assert entries[0] == "/Users/example/.nvm/versions/node/v22/bin"
    assert "/opt/homebrew/bin" in entries
    assert "/usr/local/bin" in entries
    assert entries[-2:] == ["/usr/bin", "/bin"]
    assert env["KEEP_ME"] == "yes"


def test_local_cli_env_deduplicates_existing_runtime_directory() -> None:
    env = local_cli_env(
        "/opt/homebrew/bin/gemini",
        {"PATH": "/opt/homebrew/bin:/usr/bin"},
    )

    assert env["PATH"].split(":").count("/opt/homebrew/bin") == 1
