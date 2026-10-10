"""Player view sizing and frame step. Playback itself needs a desktop window."""

from __future__ import annotations

from frameforge.ui_flet.components.player import frame_delta_ms, library_player_view, neighbor_rate


def test_frame_step_uses_twenty_four_when_fps_is_missing():
    assert frame_delta_ms(None) == 42
    assert frame_delta_ms(0) == 42
    assert frame_delta_ms(25) == 40


def test_speed_stays_inside_the_quarter_to_double_range():
    assert neighbor_rate(1.0, faster=True) == 1.25
    assert neighbor_rate(2.0, faster=True) == 2.0
    assert neighbor_rate(0.25, faster=False) == 0.25


def test_player_view_contains_the_frame_and_has_no_fixed_size():
    calls: list[str] = []
    view, video = library_player_view(
        title="Clip",
        media_paths=[__import__("pathlib").Path("clip.mp4")],
        on_close=_async_none(),
        on_open_external=lambda path: calls.append(path),
    )
    assert view.data["fit"] == "contain"
    assert view.data["kind"] == "library_player"
    assert video.width is None
    assert video.height is None
    assert video.aspect_ratio is None
    assert video.fit.value == "contain"


def _async_none():
    async def _close() -> None:
        return None

    return _close
