"""Phase 0 foundation tests — real filesystem, imports, tools, ONNX load."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


REQUIRED_PATHS = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "ARCHITECTURE.md",
    ROOT / "DECISIONS.md",
    ROOT / "LICENSE",
    ROOT / "pyproject.toml",
    ROOT / "requirements.txt",
    ROOT / "requirements-dev.txt",
    ROOT / ".gitignore",
    ROOT / ".cursorignore",
    ROOT / "docs" / "SETUP.md",
    ROOT / "docs" / "DEPENDENCIES.md",
    ROOT / "docs" / "PHASES.md",
    ROOT / "docs" / "TESTING.md",
    ROOT / "docs" / "HARDWARE.md",
    ROOT / "docs" / "COMPETITIVE.md",
    ROOT / ".cursor" / "rules" / "00-global.mdc",
    ROOT / ".cursor" / "rules" / "testing.mdc",
    ROOT / ".cursor" / "rules" / "safety.mdc",
    ROOT / ".cursor" / "rules" / "queue-sqlite.mdc",
    ROOT / ".cursor" / "rules" / "yt-dlp-ffmpeg.mdc",
    ROOT / ".cursor" / "rules" / "bulk-import.mdc",
    ROOT / ".cursor" / "rules" / "upscaling-onnx.mdc",
    ROOT / ".cursor" / "rules" / "windows-amd-hardware.mdc",
    ROOT / ".cursor" / "rules" / "gui-customtkinter.mdc",
    ROOT / ".cursor" / "rules" / "python-packaging.mdc",
    ROOT / ".cursor" / "agents" / "verifier.md",
    ROOT / ".cursor" / "agents" / "media-pipeline-expert.md",
    ROOT / ".cursor" / "agents" / "architecture-reviewer.md",
    ROOT / "src" / "frameforge" / "__init__.py",
    ROOT / "src" / "frameforge" / "__main__.py",
    ROOT / "src" / "frameforge" / "paths.py",
    ROOT / "src" / "frameforge" / "env_check.py",
    ROOT / "scripts" / "bootstrap_venv.ps1",
    ROOT / "scripts" / "download_models.ps1",
    ROOT / "scripts" / "verify_phase0.ps1",
    ROOT / "models" / ".gitkeep",
]


DOC_MARKERS = {
    ROOT / "AGENTS.md": [
        "Sequential downloads",
        "SQLite",
        "100%",
        "Downloads\\FrameForge",
        "DirectML",
    ],
    ROOT / "DECISIONS.md": [
        "CustomTkinter",
        "Sequential downloads",
        "SQLite WAL",
        "TXT/MD bulk import",
        "onnxruntime-directml",
    ],
    ROOT / "README.md": [
        "sequential",
        "SQLite",
        "bulk import",
        "CustomTkinter",
        "DirectML",
    ],
}


def test_required_paths_exist():
    missing = [str(p) for p in REQUIRED_PATHS if not p.exists()]
    assert not missing, f"Missing paths: {missing}"


def test_docs_contain_locked_decisions():
    for path, markers in DOC_MARKERS.items():
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            assert marker.lower() in text.lower(), f"{path.name} missing marker: {marker}"


def test_python_version():
    assert sys.version_info >= (3, 11)


def test_real_imports():
    import customtkinter  # noqa: F401
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    import onnxruntime  # noqa: F401
    import sqlite3  # noqa: F401
    import yt_dlp  # noqa: F401
    from PIL import Image  # noqa: F401

    assert yt_dlp is not None
    assert onnxruntime is not None


def test_cli_tools_available():
    for cmd in (
        ["ffmpeg", "-version"],
        ["aria2c", "--version"],
    ):
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        assert out.strip(), f"{cmd[0]} produced no version output"
        assert proc.returncode == 0 or "version" in out.lower() or "aria2" in out.lower()

    # yt-dlp via python module (venv entry may also exist)
    proc = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_output_dir_write_read():
    from frameforge.paths import ensure_output_tree, temp_dir

    ensure_output_tree()
    probe = temp_dir() / "phase0_probe.txt"
    probe.write_text("frameforge-phase0-ok", encoding="utf-8")
    assert probe.read_text(encoding="utf-8") == "frameforge-phase0-ok"
    probe.unlink(missing_ok=True)


def test_onnx_providers_and_model_session():
    import onnxruntime as ort

    from frameforge.paths import models_dir

    providers = ort.get_available_providers()
    assert "CPUExecutionProvider" in providers or "DmlExecutionProvider" in providers
    models = list(models_dir().glob("*.onnx"))
    assert models, "No ONNX model found under Downloads/FrameForge/models"
    preferred = (
        ["DmlExecutionProvider", "CPUExecutionProvider"]
        if "DmlExecutionProvider" in providers
        else ["CPUExecutionProvider"]
    )
    session = ort.InferenceSession(str(models[0]), providers=preferred)
    assert session is not None
    assert session.get_inputs()


def test_cli_version_and_check_env():
    proc = subprocess.run(
        [sys.executable, "-m", "frameforge", "--version"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(SRC)},
    )
    # Prefer installed package; PYTHONPATH fallback for safety
    if proc.returncode != 0 or "frameforge" not in proc.stdout:
        proc = subprocess.run(
            [sys.executable, "-m", "frameforge", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    assert proc.returncode == 0, proc.stderr
    assert "frameforge" in proc.stdout.lower()

    proc2 = subprocess.run(
        [sys.executable, "-m", "frameforge", "--check-env"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc2.returncode == 0, proc2.stderr + proc2.stdout
    report = json.loads(proc2.stdout)
    assert report["ok"] is True
    assert report["python"]["ok"] is True
