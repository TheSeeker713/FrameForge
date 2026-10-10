"""In-app library player. It replaces the grid until the user goes back."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import flet as ft

from frameforge.ui_flet.theme import COLORS, FONT_FAMILY

SPEEDS: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)


def frame_delta_ms(fps: float | None) -> int:
    """One frame in milliseconds. Unknown or unusable rates use 24 fps."""
    rate = 24.0
    if fps is not None and fps > 1:
        rate = float(fps)
    return max(1, int(round(1000.0 / rate)))


def neighbor_rate(current: float, *, faster: bool) -> float:
    rates = SPEEDS
    index = min(range(len(rates)), key=lambda i: abs(rates[i] - current))
    if faster:
        return rates[min(index + 1, len(rates) - 1)]
    return rates[max(index - 1, 0)]


async def stop_player(video: Any) -> None:
    """Await flet_video's async stop. A sync call does not run."""
    await video.stop()


def library_player_view(
    *,
    title: str,
    media_paths: list[Path],
    on_close: Callable[[], Awaitable[None]],
    on_open_external: Callable[[str], None],
    on_loaded: Callable[[], None] | None = None,
    on_failed: Callable[[], None] | None = None,
    on_position: Callable[[int], None] | None = None,
    resume_ms: int = 0,
) -> tuple[ft.Container, Any]:
    """Build the player view. ``fit`` stays CONTAIN and the size is not fixed."""
    import flet_video as ftv

    paths = [Path(path).resolve() for path in media_paths if str(path)]
    if not paths:
        raise ValueError("No media path")
    fallback = ft.Column(
        [
            ft.Text(
                "This file did not start in the app.",
                color=COLORS["text_primary"],
                font_family=FONT_FAMILY,
            ),
            ft.FilledButton(
                content="Open in another player",
                on_click=lambda _e: on_open_external(str(paths[0])),
            ),
        ],
        visible=False,
        spacing=8,
    )
    position_ms = {"value": max(0, int(resume_ms or 0))}

    def _remember(event: Any = None) -> None:
        raw = getattr(event, "position", None)
        if raw is None and event is not None:
            raw = getattr(getattr(event, "data", None), "position", None)
        if isinstance(raw, (int, float)) and raw >= 0:
            position_ms["value"] = int(raw)
            if on_position is not None:
                on_position(position_ms["value"])

    def _failed(_event: Any = None) -> None:
        fallback.visible = True
        if on_failed is not None:
            on_failed()

    def _loaded(_event: Any = None) -> None:
        fallback.visible = False
        if on_loaded is not None:
            on_loaded()

    video = ftv.Video(
        expand=True,
        playlist=[ftv.VideoMedia(str(path)) for path in paths],
        autoplay=True,
        title=title or paths[0].name,
        fit=ft.BoxFit.CONTAIN,
        volume=100,
        playback_rate=1.0,
        filter_quality=ft.FilterQuality.MEDIUM,
        on_error=_failed,
        on_load=_loaded,
        on_position_change=_remember,
    )

    async def _jump(index: int) -> None:
        await video.jump_to(index)
        if position_ms["value"] > 0:
            await video.seek(position_ms["value"])

    version_buttons: list[ft.Control] = []
    for index, path in enumerate(paths):
        version_buttons.append(
            ft.TextButton(
                content=path.name,
                on_click=lambda _e, media_index=index: _schedule(_jump(media_index)),
            )
        )

    async def _set_rate(rate: float) -> None:
        video.playback_rate = rate
        try:
            video.update()
        except Exception:  # noqa: BLE001
            pass

    def _schedule(coro: Awaitable[None]) -> None:
        # The button handler cannot await. The page task runner is attached later.
        pending = getattr(view, "pending", None)
        if callable(pending):
            pending(coro)
            return
        view.data["queued"] = coro

    view = ft.Container(
        expand=True,
        bgcolor="#0F172A",
        border_radius=12,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.TextButton(content="Back", on_click=lambda _e: _schedule(on_close())),
                        ft.Text(
                            title or paths[0].name,
                            expand=True,
                            max_lines=1,
                            color=COLORS["text_primary"],
                            font_family=FONT_FAMILY,
                        ),
                        ft.TextButton(
                            content="Open externally",
                            on_click=lambda _e: on_open_external(str(paths[0])),
                        ),
                    ]
                ),
                ft.Container(expand=True, content=video),
                fallback,
                ft.Row(version_buttons, wrap=True, spacing=4),
                ft.Row(
                    [
                        ft.TextButton(content="0.5x", on_click=lambda _e: _schedule(_set_rate(0.5))),
                        ft.TextButton(content="1x", on_click=lambda _e: _schedule(_set_rate(1.0))),
                        ft.TextButton(content="1.5x", on_click=lambda _e: _schedule(_set_rate(1.5))),
                        ft.TextButton(content="2x", on_click=lambda _e: _schedule(_set_rate(2.0))),
                    ]
                ),
            ],
            expand=True,
            spacing=8,
        ),
        data={
            "kind": "library_player",
            "path": str(paths[0]),
            "paths": [str(path) for path in paths],
            "fit": "contain",
            "resume_ms": position_ms["value"],
        },
    )
    view.data["position"] = position_ms
    return view, video
