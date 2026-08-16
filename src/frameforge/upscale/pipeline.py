"""End-to-end upscale pipeline with stop/resume checkpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from frameforge.paths import ensure_output_tree, temp_dir, upscaled_dir
from frameforge.queue.process_registry import ProcessRegistry
from frameforge.upscale.disk import (
    DEFAULT_MAX_DURATION_MINUTES,
    assert_upscale_guards,
    cleanup_job_frames,
    free_bytes_for,
    video_metrics,
)
from frameforge.upscale.ffmpeg_utils import (
    assemble_video,
    detect_fps,
    extract_audio,
    extract_frames,
    video_size,
)
from frameforge.upscale.guards import assert_upscale_allowed
from frameforge.upscale.onnx_upscaler import OnnxUpscaler
from frameforge.util.process_tree import DownloadCancelled, DownloadPaused


ProgressCb = Callable[[float], None]


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
    ) -> None:
        ensure_output_tree()
        self.upscaler = OnnxUpscaler(model_path=model_path, tile=tile)
        self.work_root = work_root or temp_dir()
        self.max_frames = max_frames
        self.max_duration_minutes = max_duration_minutes
        self.keep_frames = keep_frames

    def _job_dirs(self, job_key: str) -> dict[str, Path]:
        base = self.work_root / job_key
        return {
            "base": base,
            "frames": base / "frames",
            "upscaled": base / "upscaled_frames",
            "audio": base / "audio.m4a",
            "checkpoint": base / "checkpoint.json",
        }

    def _load_checkpoint(self, path: Path) -> dict:
        if not path.exists():
            return {"completed_frames": 0}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_checkpoint(self, path: Path, completed_frames: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"completed_frames": completed_frames}),
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
        dirs = self._job_dirs(job_key)
        in_w, in_h = assert_upscale_allowed(input_video)
        metrics = video_metrics(input_video)
        assert_upscale_guards(
            metrics,
            max_frames=self.max_frames,
            max_duration_minutes=self.max_duration_minutes,
            free_bytes=free_bytes_for(self.work_root),
            volume=str(self.work_root),
        )
        dirs["base"].mkdir(parents=True, exist_ok=True)
        success = False
        resumable = False
        try:
            frames = extract_frames(
                input_video,
                dirs["frames"],
                max_frames=self.max_frames,
                job_id=job_id,
                process_registry=process_registry,
            )
            ckpt = self._load_checkpoint(dirs["checkpoint"])
            start = int(ckpt.get("completed_frames", 0))

            def frame_progress(pct: float) -> None:
                if progress_cb:
                    # frame upscale is majority of work
                    progress_cb(min(95.0, pct * 0.95))

            completed = self.upscaler.upscale_frames(
                frames,
                dirs["upscaled"],
                start_index=start,
                progress_cb=frame_progress,
                should_stop=should_stop,
            )
            self._save_checkpoint(dirs["checkpoint"], completed)
            if should_stop and should_stop() and completed < len(frames):
                raise DownloadCancelled(f"upscale stopped at frame {completed}/{len(frames)}")

            audio = extract_audio(
                input_video,
                dirs["audio"],
                job_id=job_id,
                process_registry=process_registry,
            )
            fps = detect_fps(input_video)
            out = output_path or (upscaled_dir() / f"{input_video.stem}.upscaled.mp4")
            assemble_video(
                dirs["upscaled"],
                out,
                fps=fps,
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
                frames_processed=completed,
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
