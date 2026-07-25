"""Regression checks that keep MeowWorker distinct from upstream releases."""

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

    assert config["productName"] == "MeowWorker"
    assert config["identifier"] == "com.dennykim.meowworker"
    assert config["version"] == "0.2.0"

    endpoints = config["plugins"]["updater"]["endpoints"]
    assert endpoints == [
        "https://github.com/dennykim123/meowworker/"
        "releases/latest/download/latest.json"
    ]
    assert all("andrewyng/openworker" not in endpoint for endpoint in endpoints)
    assert all("download.openworker.com" not in endpoint for endpoint in endpoints)


def test_readme_leads_with_independent_product_disclosure() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.startswith("# MeowWorker\n")
    assert "Your AI coworker that gets things done." in readme
    assert "Built on [OpenWorker]" in readme
    assert "MeowWorker is an independent product built from the open-source OpenWorker project." in readme
    assert "not affiliated with OpenWorker, OpenAI, Anthropic, or Google" in readme


def test_release_artifacts_use_the_meowworker_name() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    manifest = (ROOT / "packaging/make_update_manifest.py").read_text(
        encoding="utf-8"
    )

    stable_names = (
        "MeowWorker-macos-arm64.app.tar.gz",
        "MeowWorker-windows-setup.exe",
    )
    for name in stable_names:
        assert name in manifest
        workflow_name = name.replace(
            "macos-arm64.app.tar.gz", "${{ matrix.slug }}.app.tar.gz"
        )
        assert workflow_name in workflow or name in workflow

    assert "OpenWorker-Subscription-Bridge" not in workflow
    assert "OpenWorker-Subscription-Bridge" not in manifest
