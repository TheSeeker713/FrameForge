"""Download → optional upscale orchestration helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from frameforge.convert.handler import make_convert_handler
from frameforge.db.repository import JobRepository
from frameforge.download.handler import make_download_handler
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import ensure_output_tree, temp_dir
from frameforge.queue.worker import SequentialWorker
from frameforge.upscale.bootstrap import bootstrap_models
from frameforge.upscale.handler import make_upscale_handler
from frameforge.upscale.pipeline import UpscalePipeline


def build_worker(
    repo: JobRepository,
    *,
    downloader: YtDlpDownloader | None = None,
    upscale_pipeline: UpscalePipeline | None = None,
) -> SequentialWorker:
    ensure_output_tree()
    bootstrap_models()
    # Build worker first so handlers share its ProcessRegistry for hard cancel.
    worker = SequentialWorker(
        repo,
        download_handler=lambda j, r: None,
        upscale_handler=None,
        poll_interval=0.05,
    )
    pipe = upscale_pipeline or UpscalePipeline()
    worker.upscale_pipeline = pipe
    worker.download_handler = make_download_handler(
        downloader, process_registry=worker.processes
    )
    worker.upscale_handler = make_upscale_handler(
        pipe, process_registry=worker.processes
    )
    worker.convert_handler = make_convert_handler(process_registry=worker.processes)
    return worker


def aggregate_progress(status: str, stage_progress: float, upscale: bool) -> float:
    """Map stage progress into overall 0-100 when chaining."""
    p = max(0.0, min(100.0, stage_progress))
    if not upscale:
        return p
    if status in ("pending",):
        return 0.0
    if status == "downloading":
        return p * 0.5
    if status in ("download_completed",):
        return 50.0
    if status == "upscaling":
        return 50.0 + p * 0.5
    if status == "completed":
        return 100.0
    return p


def cleanup_job_temp(job_id: int, work_root: Path | None = None) -> None:
    root = (work_root or temp_dir()) / f"job_{job_id}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
