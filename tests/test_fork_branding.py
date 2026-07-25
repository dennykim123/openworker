"""Regression checks that keep the community fork distinct from upstream releases."""

from __future__ import annotations

import json
from pathlib import Path

from coworker.secrets import state_dir


ROOT = Path(__file__).resolve().parents[1]


def test_existing_state_directory_is_preserved(tmp_path, monkeypatch) -> None:
    """Renaming the app must not orphan conversations, settings, or credentials."""
    monkeypatch.delenv("COWORKER_STATE_DIR", raising=False)
    monkeypatch.setattr("coworker.secrets.sys.platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert state_dir() == tmp_path / ".config" / "coworker"


def test_desktop_identity_and_update_channel_are_fork_specific() -> None:
    config = json.loads(
        (ROOT / "surfaces/gui/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    )

    assert config["productName"] == "OpenWorker Subscription Bridge"
    assert config["identifier"] == "com.dennykim.openworkersubscriptionbridge"
    assert config["version"] == "0.1.9"

    endpoints = config["plugins"]["updater"]["endpoints"]
    assert endpoints == [
        "https://github.com/dennykim123/openworker-subscription-bridge/"
        "releases/latest/download/latest.json"
    ]
    assert all("andrewyng/openworker" not in endpoint for endpoint in endpoints)
    assert all("download.openworker.com" not in endpoint for endpoint in endpoints)


def test_readme_leads_with_unofficial_fork_disclosure() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.startswith("# OpenWorker Subscription Bridge\n")
    assert "Unofficial community fork of OpenWorker" in readme
    assert "not affiliated with OpenWorker, OpenAI, Anthropic, or Google" in readme


def test_release_artifacts_use_the_bridge_name() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    manifest = (ROOT / "packaging/make_update_manifest.py").read_text(
        encoding="utf-8"
    )

    stable_names = (
        "OpenWorker-Subscription-Bridge-macos-arm64.app.tar.gz",
        "OpenWorker-Subscription-Bridge-windows-setup.exe",
    )
    for name in stable_names:
        assert name in manifest
        workflow_name = name.replace(
            "macos-arm64.app.tar.gz", "${{ matrix.slug }}.app.tar.gz"
        )
        assert workflow_name in workflow or name in workflow

    assert "out/OpenWorker-windows-setup.exe" not in workflow
    assert "out/OpenWorker-macos-arm64.dmg" not in workflow
