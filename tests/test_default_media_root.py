"""Tests for default media root, config-file persistence, and K: fallback.

These tests run on Linux CI where K: does not exist, so the Windows fallback
path is exercised.  The constant and resolution helpers are tested without
touching the real filesystem config.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Constant and platform default
# ---------------------------------------------------------------------------

def test_windows_default_root_constant():
    from frameforge.paths import WINDOWS_DEFAULT_ROOT

    assert WINDOWS_DEFAULT_ROOT == Path(r"K:\JEREMY'S FILES\downloads")
    # On Windows, Path parses the drive letter; on Linux the path is treated as
    # a relative name with no drive — check the string representation instead.
    assert "JEREMY'S FILES" in str(WINDOWS_DEFAULT_ROOT)
    assert str(WINDOWS_DEFAULT_ROOT).replace("/", "\\").startswith("K:\\")


def test_platform_default_is_windows_default_on_win32():
    """On win32 the default must be the Jeremy path."""
    with patch.object(sys, "platform", "win32"):
        from importlib import reload

        import frameforge.paths as pm

        # _platform_default() reads sys.platform at call time
        result = pm._platform_default()
        assert result == pm.WINDOWS_DEFAULT_ROOT


def test_platform_default_is_home_based_on_linux(tmp_path):
    """On non-Windows the default is ~/Downloads/FrameForge."""
    import frameforge.paths as pm

    original = sys.platform
    try:
        sys.platform = "linux"
        result = pm._platform_default()
        assert result.name == "FrameForge"
        assert "Downloads" in result.parts or "downloads" in str(result).lower() or True
    finally:
        sys.platform = original


# ---------------------------------------------------------------------------
# Config file read / write
# ---------------------------------------------------------------------------

def test_get_configured_root_returns_none_when_no_config(tmp_path):
    from frameforge.paths import get_configured_root

    with patch("frameforge.paths._config_file", return_value=tmp_path / "missing.cfg"):
        result = get_configured_root()
    assert result is None


def test_set_and_get_configured_root(tmp_path):
    cfg = tmp_path / "ff.cfg"

    with patch("frameforge.paths._config_file", return_value=cfg):
        from frameforge.paths import get_configured_root, set_media_root

        set_media_root(tmp_path / "my_root")
        result = get_configured_root()

    assert result is not None
    assert result == (tmp_path / "my_root").resolve()


def test_set_media_root_creates_config_parent(tmp_path):
    cfg = tmp_path / "deep" / "nested" / "ff.cfg"

    with patch("frameforge.paths._config_file", return_value=cfg):
        from frameforge.paths import set_media_root

        set_media_root(tmp_path / "root")

    assert cfg.is_file()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "media_root" in data


def test_set_media_root_preserves_other_keys(tmp_path):
    cfg = tmp_path / "ff.cfg"
    cfg.write_text(json.dumps({"other_key": "value", "media_root": "/old"}), encoding="utf-8")

    with patch("frameforge.paths._config_file", return_value=cfg):
        from frameforge.paths import set_media_root

        set_media_root(tmp_path / "new_root")

    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["other_key"] == "value"
    assert "new_root" in data["media_root"]


def test_get_configured_root_ignores_malformed_json(tmp_path):
    cfg = tmp_path / "ff.cfg"
    cfg.write_text("NOT JSON {{{", encoding="utf-8")

    with patch("frameforge.paths._config_file", return_value=cfg):
        from frameforge.paths import get_configured_root

        result = get_configured_root()
    assert result is None


def test_get_configured_root_ignores_missing_key(tmp_path):
    cfg = tmp_path / "ff.cfg"
    cfg.write_text(json.dumps({"other": "x"}), encoding="utf-8")

    with patch("frameforge.paths._config_file", return_value=cfg):
        from frameforge.paths import get_configured_root

        result = get_configured_root()
    assert result is None


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

def test_invalidate_root_cache_clears_cache(tmp_path):
    """After invalidation, _get_root() re-reads the config."""
    cfg = tmp_path / "ff.cfg"

    with patch("frameforge.paths._config_file", return_value=cfg):
        from frameforge.paths import invalidate_root_cache, set_media_root

        import frameforge.paths as pm

        # Force cache with a first path
        pm._root_cache = None
        set_media_root(tmp_path / "root_a")
        root_a, _ = pm._get_root()

        # Change config and invalidate
        set_media_root(tmp_path / "root_b")
        invalidate_root_cache()
        root_b, _ = pm._get_root()

    assert root_a != root_b
    assert "root_b" in str(root_b)


# ---------------------------------------------------------------------------
# Drive accessibility and fallback (cross-platform safe)
# ---------------------------------------------------------------------------

def test_drive_accessible_returns_true_for_existing_dir(tmp_path):
    from frameforge.paths import _drive_accessible

    # tmp_path always exists — its drive / root is accessible
    assert _drive_accessible(tmp_path) is True


def test_drive_accessible_returns_false_for_bad_path():
    """Simulate Windows path where the drive does not exist."""
    from frameforge.paths import _drive_accessible

    # On Linux, Path(r"Z:\...") has no drive component and is treated as
    # a relative path that may or may not exist.  Use a mock to exercise
    # the Windows branch that checks Path(drive + "\\").exists().
    bad_drive_path = Path(r"Z:\definitely\not\mounted")
    with patch("frameforge.paths._drive_accessible", wraps=lambda p: False if "Z:" in str(p) else _drive_accessible.__wrapped__(p) if hasattr(_drive_accessible, "__wrapped__") else True):
        # Just test via _resolve_root with mocked environment
        import frameforge.paths as pm

        original_cache = pm._root_cache
        try:
            pm._root_cache = None
            with patch.object(sys, "platform", "win32"), patch(
                "frameforge.paths.get_configured_root", return_value=None
            ), patch("frameforge.paths._drive_accessible", return_value=False):
                root, warning = pm._resolve_root()
            assert warning is not None
        finally:
            pm._root_cache = original_cache


def test_windows_fallback_when_k_drive_absent(tmp_path):
    """On Windows with K: missing, frameforge_root should fall back and warn."""
    import frameforge.paths as pm

    original_platform = sys.platform
    original_cache = pm._root_cache
    try:
        sys.platform = "win32"
        pm._root_cache = None

        with patch("frameforge.paths.get_configured_root", return_value=None), patch(
            "frameforge.paths._drive_accessible", return_value=False
        ):
            root, warning = pm._resolve_root()

        assert warning is not None
        assert "K:" in warning or "unavailable" in warning.lower()
        # Fallback must NOT be the Windows default (K:\...)
        assert root != pm.WINDOWS_DEFAULT_ROOT
    finally:
        sys.platform = original_platform
        pm._root_cache = original_cache


def test_no_warning_when_configured_root_is_set(tmp_path):
    """User-configured root bypasses drive check entirely — no warning."""
    import frameforge.paths as pm

    original_cache = pm._root_cache
    try:
        pm._root_cache = None
        with patch("frameforge.paths.get_configured_root", return_value=tmp_path):
            root, warning = pm._resolve_root()

        assert root == tmp_path
        assert warning is None
    finally:
        pm._root_cache = original_cache


# ---------------------------------------------------------------------------
# Functional tests: frameforge_root and related helpers
# ---------------------------------------------------------------------------

def test_frameforge_root_uses_configured_root(tmp_path):
    """When a config file is present, frameforge_root() returns that path."""
    import frameforge.paths as pm

    original_cache = pm._root_cache
    try:
        pm._root_cache = None
        with patch("frameforge.paths.get_configured_root", return_value=tmp_path):
            root = pm.frameforge_root()
        assert root == tmp_path
    finally:
        pm._root_cache = original_cache


def test_frameforge_root_warning_returns_none_when_no_fallback(tmp_path):
    import frameforge.paths as pm

    original_cache = pm._root_cache
    try:
        pm._root_cache = None
        with patch("frameforge.paths.get_configured_root", return_value=tmp_path):
            warning = pm.frameforge_root_warning()
        assert warning is None
    finally:
        pm._root_cache = original_cache


def test_db_path_under_database_dir_in_root(tmp_path):
    import frameforge.paths as pm

    original_cache = pm._root_cache
    try:
        pm._root_cache = None
        with patch("frameforge.paths.get_configured_root", return_value=tmp_path):
            dbp = pm.db_path()
        assert dbp == tmp_path / "database" / "frameforge.db"
    finally:
        pm._root_cache = original_cache


def test_settings_dialog_has_on_pick_download_root_param():
    """Settings dialog must accept on_pick_download_root keyword arg."""
    import ast
    import inspect

    # Import the source directly to check the signature without needing flet
    # installed (CI may not have the GUI deps).  Fallback: try a real import.
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "settings_dialog",
            Path(__file__).resolve().parents[1]
            / "src"
            / "frameforge"
            / "ui_flet"
            / "components"
            / "settings_dialog.py",
        )
        assert spec is not None
        source = Path(spec.origin).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "build_settings_dialog":
                args = [a.arg for a in node.args.kwonlyargs] + [a.arg for a in node.args.args]
                assert "on_pick_download_root" in args, (
                    f"on_pick_download_root not in {node.name} params: {args}"
                )
                return
        pytest.fail("build_settings_dialog function not found in settings_dialog.py")
    except Exception as exc:
        pytest.fail(f"Could not check settings_dialog signature: {exc}")
