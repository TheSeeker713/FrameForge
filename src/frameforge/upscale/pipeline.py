"""End-to-end chunked upscale pipeline with stop/resume checkpoints."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from frameforge.paths import ensure_output_tree, temp_dir, upscaled_dir
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.upscale.disk import (
    DEFAULT_CHUNK_FRAMES,
    DEFAULT_MAX_DURATION_MINUTES,
    SEGMENT_DIR_NAME,
    assert_upscale_guards,
    cleanup_job_frames,
    duration_warning_message,
    free_bytes_for,
    video_metrics,
)
from frameforge.upscale.ffmpeg_utils import (
    assemble_video,
    concat_segments,
    extract_audio,
    extract_frame_range,
    mux_video_audio,
    video_size,
)
from frameforge.upscale.guards import assert_upscale_allowed
from frameforge.upscale.onnx_upscaler import OnnxUpscaler, UpscaleConfigError
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused


ProgressCb = Callable[[float], None]
log = logging.getLogger(__name__)


@dataclass
class UpscaleResult:
    output_path: Path
    input_size: tuple[int, int]
    output_size: tuple[int, int]
    frames_processed: int
    provider: str


class UpscalePipeline:
    def __init__(
        self,
        *,
        model_path: Path | None = None,
        tile: int = 128,
        work_root: Path | None = None,
        max_frames: int | None = None,
        max_duration_minutes: float | None = DEFAULT_MAX_DURATION_MINUTES,
        keep_frames: bool = False,
        chunk_frames: int = DEFAULT_CHUNK_FRAMES,
    ) -> None:
        ensure_output_tree()
        self._explicit_model = model_path
        self._tile = tile
        self.upscaler = OnnxUpscaler(model_path=model_path, tile=tile)
        self.work_root = work_root or temp_dir()
        self.max_frames = max_frames
        self.max_duration_minutes = max_duration_minutes
        self.keep_frames = keep_frames
        self.chunk_frames = max(1, int(chunk_frames))

    @property
    def upscale_available(self) -> bool:
        return bool(self.upscaler.available)

    @property
    def upscale_unavailable_reason(self) -> str | None:
        if self.upscaler.available:
            return None
        return self.upscaler.unavailable_reason

    def reload_model(self) -> None:
        self.upscaler.reload(self._explicit_model)

    def _job_dirs(self, job_key: str) -> dict[str, Path]:
        base = self.work_root / job_key
        return {
            "base": base,
            "frames": base / "frames",
            "upscaled": base / "upscaled_frames",
            "segments": base / SEGMENT_DIR_NAME,
            "audio": base / "audio.m4a",
            "checkpoint": base / "checkpoint.json",
            "concat": base / "video_only.mp4",
        }

    def _load_checkpoint(self, path: Path) -> dict:
        if not path.exists():
            return {"completed_frames": 0, "completed_chunks": 0}
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("completed_frames", 0)
        data.setdefault("completed_chunks", 0)
        return data

    def _save_checkpoint(
        self,
        path: Path,
        *,
        completed_frames: int,
        completed_chunks: int,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "completed_frames": int(completed_frames),
                    "completed_chunks": int(completed_chunks),
                }
            ),
            encoding="utf-8",
        )

    def run(
        self,
        input_video: Path,
        *,
        job_key: str,
        output_path: Path | None = None,
        progress_cb: ProgressCb | None = None,
        should_stop: Callable[[], bool] | None = None,
        job_id: int | None = None,
        process_registry: ProcessRegistry | None = None,
    ) -> UpscaleResult:
        input_video = Path(input_video)
        if not self.upscaler.available:
            self.reload_model()
        if not self.upscaler.available:
            raise UpscaleConfigError(self.upscale_unavailable_reason)
        dirs = self._job_dirs(job_key)
        in_w, in_h = assert_upscale_allowed(input_video)
        metrics = video_metrics(input_video)
        warn = duration_warning_message(metrics, warn_minutes=self.max_duration_minutes)
        if warn:
            log.warning(warn)
        chunk_n = max(1, int(self.chunk_frames))
        assert_upscale_guards(
            metrics,
            max_frames=self.max_frames,
            max_duration_minutes=None,
            chunk_frames=chunk_n,
            free_bytes=free_bytes_for(self.work_root),
            volume=str(self.work_root),
        )
        dirs["base"].mkdir(parents=True, exist_ok=True)
        dirs["segments"].mkdir(parents=True, exist_ok=True)
        success = False
        resumable = False
        fps = metrics.fps
        total_frames = max(1, int(math.ceil(metrics.duration_sec * max(1.0, fps))))
        if self.max_frames is not None:
            total_frames = min(total_frames, max(1, int(self.max_frames)))
        n_chunks = max(1, int(math.ceil(total_frames / chunk_n)))
        try:
            ckpt = self._load_checkpoint(dirs["checkpoint"])
            completed_frames = int(ckpt.get("completed_frames", 0))
            completed_chunks = int(ckpt.get("completed_chunks", 0))

            for ci in range(n_chunks):
                if should_stop and should_stop():
                    raise DownloadCancelled(
                        f"upscale stopped at chunk {ci}/{n_chunks}"
                    )
                chunk_start = ci * chunk_n
                this_count = min(chunk_n, total_frames - chunk_start)
                if this_count <= 0:
                    break
                if completed_chunks > ci:
                    continue

                src_frames = list(dirs["frames"].glob("frame_*.png")) if dirs["frames"].is_dir() else []
                if ci != completed_chunks or len(src_frames) < this_count:
                    frames = extract_frame_range(
                        input_video,
                        dirs["frames"],
                        start_frame=chunk_start,
                        count=this_count,
                        fps=fps,
                        job_id=job_id,
                        process_registry=process_registry,
                    )
                else:
                    frames = sorted(src_frames)[:this_count]
                this_count = min(this_count, len(frames))
                if this_count <= 0:
                    break
                onnx_start = 0
                if ci == completed_chunks and completed_frames > chunk_start:
                    onnx_start = min(this_count, max(0, completed_frames - chunk_start))
                    up_existing = (
                        list(dirs["upscaled"].glob("frame_*.png"))
                        if dirs["upscaled"].is_dir()
                        else []
                    )
                    if len(up_existing) < onnx_start:
                        onnx_start = len(up_existing)

                def chunk_progress(pct: float) -> None:
                    if not progress_cb:
                        return
                    local_done = pct / 100.0 * this_count
                    overall = (chunk_start + local_done) * 100.0 / total_frames
                    progress_cb(min(95.0, overall * 0.95))

                completed_local = self.upscaler.upscale_frames(
                    frames,
                    dirs["upscaled"],
                    start_index=onnx_start,
                    progress_cb=chunk_progress,
                    should_stop=should_stop,
                )
                self._save_checkpoint(
                    dirs["checkpoint"],
                    completed_frames=chunk_start + completed_local,
                    completed_chunks=ci,
                )
                if should_stop and should_stop() and completed_local < len(frames):
                    raise DownloadCancelled(
                        f"upscale stopped at frame {chunk_start + completed_local}/{total_frames}"
                    )

                seg = dirs["segments"] / f"chunk_{ci:04d}.mp4"
                assemble_video(
                    dirs["upscaled"],
                    seg,
                    fps=fps,
                    audio_path=None,
                    metadata_source=None,
                    job_id=job_id,
                    process_registry=process_registry,
                )
                if not self.keep_frames:
                    cleanup_job_frames(dirs["base"], include_job_dir=False)
                completed_chunks = ci + 1
                completed_frames = chunk_start + this_count
                self._save_checkpoint(
                    dirs["checkpoint"],
                    completed_frames=completed_frames,
                    completed_chunks=completed_chunks,
                )
                if this_count < chunk_n:
                    break

            if should_stop and should_stop():
                raise DownloadCancelled("upscale stopped before mux")

            audio = extract_audio(
                input_video,
                dirs["audio"],
                job_id=job_id,
                process_registry=process_registry,
            )
            segments = sorted(dirs["segments"].glob("chunk_*.mp4"))
            concat_segments(
                segments,
                dirs["concat"],
                job_id=job_id,
                process_registry=process_registry,
            )
            out = output_path or (upscaled_dir() / f"{input_video.stem}.upscaled.mp4")
            mux_video_audio(
                dirs["concat"],
                out,
                audio_path=audio,
                metadata_source=input_video,
                job_id=job_id,
                process_registry=process_registry,
            )
            if progress_cb:
                progress_cb(100.0)
            out_w, out_h = video_size(out)
            success = True
            return UpscaleResult(
                output_path=out,
                input_size=(in_w, in_h),
                output_size=(out_w, out_h),
                frames_processed=completed_frames,
                provider=self.upscaler.provider,
            )
        except (DownloadCancelled, DownloadPaused):
            resumable = True
            raise
        finally:
            if success:
                cleanup_job_frames(dirs["base"], include_job_dir=True)
            elif not resumable and not self.keep_frames:
                cleanup_job_frames(dirs["base"], include_job_dir=False)
