"""In-app library player. Queue playback stays on the OS default app."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import flet as ft

from frameforge.ui_flet.elevation import elevated_outlined_button
from frameforge.ui_flet.theme import COLORS


def library_player_dialog(
    *,
    title: str,
    media_path: Path,
    on_close: Any,
) -> tuple[ft.AlertDialog, Any]:
    """Build a modal player for a local file. Returns ``(dialog, video)``."""
    import flet_video as ftv

    path = Path(media_path).resolve()
    video = ftv.Video(
        width=760,
        height=428,
        expand=False,
        playlist=[ftv.VideoMedia(str(path))],
        autoplay=True,
        title=title or path.name,
        aspect_ratio=16 / 9,
        volume=100,
        fill_color=COLORS["text_primary"],
    )

    def close(_e: Any = None) -> None:
        try:
            video.stop()
        except Exception:  # noqa: BLE001
            pass
        on_close()

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text(title or path.name, max_lines=2),
        content=ft.Container(
            width=760,
            height=428,
            bgcolor="#0F172A",
            border_radius=8,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=video,
        ),
        actions=[elevated_outlined_button("Close", on_click=close)],
        data={"kind": "library_player", "path": str(path)},
    )
    dlg.on_dismiss = close
    return dlg, video
