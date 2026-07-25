"""Environment helpers for CLI runtimes launched from desktop app bundles."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional


def local_cli_env(
    executable: Optional[str], base: Optional[Mapping[str, str]] = None
) -> dict[str, str]:
    """Ensure a CLI's sibling interpreter is visible outside terminal shells.

    macOS GUI apps receive a minimal PATH that commonly omits Homebrew, npm,
    nvm, and other user-level install locations. Node-based CLIs use
    ``#!/usr/bin/env node``, so finding the CLI alone is insufficient unless its
    containing directory is also present while the process starts.
    """
    env = dict(base) if base is not None else os.environ.copy()
    current = [part for part in env.get("PATH", "").split(os.pathsep) if part]
    candidates = [
        str(Path(executable).expanduser().parent) if executable else "",
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    ordered: list[str] = []
    for candidate in [*candidates, *current]:
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    env["PATH"] = os.pathsep.join(ordered)
    return env
