"""Packaging spec is Flet-oriented and one-folder (no network, no build)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "frameforge.spec"


def test_spec_targets_flet_one_folder():
    text = SPEC.read_text(encoding="utf-8")
    assert "flet" in text
    assert "flet_desktop" in text
    assert "frameforge.ui_flet.app" in text
    assert "COLLECT(" in text
    assert "exclude_binaries=True" in text
    assert "flet-client" in text
    assert "pyi_rth_flet_view.py" in text
    hook = ROOT / "packaging" / "pyi_rth_flet_view.py"
    assert hook.is_file()
    assert "FLET_VIEW_PATH" in hook.read_text(encoding="utf-8")
    assert "_internal" in hook.read_text(encoding="utf-8")
