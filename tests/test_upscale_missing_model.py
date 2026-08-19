"""GUI/worker must start with an empty models dir (no ONNX)."""

from __future__ import annotations

from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.errors import UPSCALE_CONFIG, UNKNOWN, classify_error
from frameforge.pipeline import build_worker
from frameforge.upscale.handler import make_upscale_handler
from frameforge.upscale.onnx_upscaler import (
    OnnxUpscaler,
    UpscaleConfigError,
    find_model,
    pick_model,
)
from frameforge.upscale.pipeline import UpscalePipeline
from frameforge.ui_flet.app import create_ui, FrameForgeUi


def _empty_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    empty = tmp_path / "models"
    empty.mkdir()
    monkeypatch.setattr("frameforge.upscale.onnx_upscaler.models_dir", lambda: empty)
    monkeypatch.setattr("frameforge.upscale.bootstrap.models_dir", lambda: empty)
    monkeypatch.setattr("frameforge.pipeline.bootstrap_models", lambda: empty)
    monkeypatch.setattr("frameforge.upscale.bootstrap.maybe_create_smoke_onnx", lambda **_k: None)
    return empty


def test_pick_model_empty_dir_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    empty = _empty_models(tmp_path, monkeypatch)
    assert find_model(root=empty) is None
    assert pick_model() is None


def test_onnx_upscaler_empty_dir_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _empty_models(tmp_path, monkeypatch)
    up = OnnxUpscaler()
    assert up.available is False
    assert "No ONNX model" in (up.unavailable_reason or "")


def test_build_worker_empty_models_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _empty_models(tmp_path, monkeypatch)
    repo = JobRepository(tmp_path / "w.db")
    worker = build_worker(repo)
    pipe = worker.upscale_pipeline
    assert pipe is not None
    assert pipe.upscale_available is False
    assert "No ONNX model" in (pipe.upscale_unavailable_reason or "")
    repo.close()


def test_create_ui_empty_models_does_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _empty_models(tmp_path, monkeypatch)
    repo = JobRepository(tmp_path / "g.db")
    ui = create_ui(repo=repo, start_worker=False, recover_on_launch=False)
    assert isinstance(ui, FrameForgeUi)
    assert ui.worker.upscale_pipeline is not None
    assert ui.worker.upscale_pipeline.upscale_available is False
    ui.shutdown()
    repo.close()


def test_upscale_handler_reports_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _empty_models(tmp_path, monkeypatch)
    pipe = UpscalePipeline(work_root=tmp_path / "work")
    assert pipe.upscale_available is False
    handler = make_upscale_handler(pipe)
    repo = JobRepository(tmp_path / "h.db")
    job = repo.enqueue("https://example.com/u")
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"not-a-real-video")
    repo.set_paths(job.id, download_path=str(src), output_path=str(src))
    with pytest.raises(UpscaleConfigError) as caught:
        handler(repo.get(job.id), repo)
    assert caught.value.category == UPSCALE_CONFIG
    assert classify_error(str(caught.value)) == UPSCALE_CONFIG
    assert classify_error(str(caught.value)) != UNKNOWN
    assert "download_models" in str(caught.value).lower() or "smoke" in str(caught.value).lower()
    repo.close()
