"""Dependency and environment probes used by CLI and Phase 0 tests."""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from typing import Any

from frameforge.paths import ensure_output_tree, models_dir


def _tool_version(cmd: list[str]) -> dict[str, Any]:
    exe = shutil.which(cmd[0])
    if not exe:
        return {"ok": False, "path": None, "version": None, "error": f"{cmd[0]} not on PATH"}
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        first = text.strip().splitlines()[0] if text.strip() else ""
        return {
            "ok": proc.returncode == 0 or bool(first),
            "path": exe,
            "version": first,
            "returncode": proc.returncode,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": exe, "version": None, "error": str(exc)}


def _try_import(name: str) -> dict[str, Any]:
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", None)
        return {"ok": True, "version": version}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def check_onnx_providers() -> dict[str, Any]:
    try:
        import onnxruntime as ort

        providers = list(ort.get_available_providers())
        has_dml = "DmlExecutionProvider" in providers
        has_cpu = "CPUExecutionProvider" in providers
        model_files = sorted(models_dir().glob("*.onnx"))
        session_ok = False
        session_error = None
        if model_files:
            try:
                preferred = (
                    ["DmlExecutionProvider", "CPUExecutionProvider"]
                    if has_dml
                    else ["CPUExecutionProvider"]
                )
                ort.InferenceSession(str(model_files[0]), providers=preferred)
                session_ok = True
            except Exception as exc:  # noqa: BLE001
                session_error = str(exc)
        return {
            "ok": has_dml or has_cpu,
            "providers": providers,
            "has_dml": has_dml,
            "has_cpu": has_cpu,
            "model_count": len(model_files),
            "session_ok": session_ok,
            "session_error": session_error,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def check_environment() -> dict[str, Any]:
    ensure_output_tree()
    python = {
        "ok": sys.version_info >= (3, 11),
        "version": sys.version.split()[0],
        "executable": sys.executable,
    }
    packages = {
        "yt_dlp": _try_import("yt_dlp"),
        "onnxruntime": _try_import("onnxruntime"),
        "customtkinter": _try_import("customtkinter"),
        "cv2": _try_import("cv2"),
        "numpy": _try_import("numpy"),
        "PIL": _try_import("PIL"),
        "sqlite3": _try_import("sqlite3"),
    }
    tools = {
        "ffmpeg": _tool_version(["ffmpeg", "-version"]),
        "aria2c": _tool_version(["aria2c", "--version"]),
        "yt-dlp": _tool_version(["yt-dlp", "--version"]),
    }
    onnx = check_onnx_providers()
    ok = (
        python["ok"]
        and all(p["ok"] for p in packages.values())
        and tools["ffmpeg"]["ok"]
        and tools["aria2c"]["ok"]
        and (tools["yt-dlp"]["ok"] or packages["yt_dlp"]["ok"])
        and onnx["ok"]
    )
    return {
        "ok": ok,
        "python": python,
        "packages": packages,
        "tools": tools,
        "onnx": onnx,
        "notes": [
            "Sequential downloads only",
            "SQLite WAL queue",
            "Bulk TXT/MD import",
            "DirectML preferred",
        ],
    }
