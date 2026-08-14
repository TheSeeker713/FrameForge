"""Widget-level hover elevation. Never touch page.window.shadow (drag-ghost)."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.ui_flet.theme import (
    COLORS,
    ELEVATION_HOVER,
    ELEVATION_PRESS,
    ELEVATION_REST,
    ELEVATION_SELECTED,
)

CS = ft.ControlState


def shadow_from_spec(spec: dict[str, Any]) -> ft.BoxShadow:
    ox, oy = spec["offset"]
    return ft.BoxShadow(
        blur_radius=spec["blur_radius"],
        spread_radius=spec.get("spread_radius", 0),
        color=spec["color"],
        offset=ft.Offset(ox, oy),
    )


def elevation_bundle(
    *,
    rest: dict[str, Any] | None = None,
    hover: dict[str, Any] | None = None,
    press: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "rest": dict(rest or ELEVATION_REST),
        "hover": dict(hover or ELEVATION_HOVER),
        "press": dict(press or ELEVATION_PRESS),
    }


def _hover_on(e: Any) -> bool | None:
    data = getattr(e, "data", None)
    if data is None:
        return None
    if data in (True, False):
        return bool(data)
    text = str(data).strip().lower()
    if text in {"true", "1", "hover", "entered"}:
        return True
    if text in {"false", "0", "exit", "exited"}:
        return False
    return None


def bind_hover_elevation(
    ctrl: ft.Container,
    *,
    selected: bool = False,
    disabled: bool = False,
) -> ft.Container:
    """Swap Container.shadow on hover. Disabled controls stay flat."""
    rest = ELEVATION_SELECTED if selected else ELEVATION_REST
    bundle = elevation_bundle(rest=rest)
    data = dict(ctrl.data or {})
    data["elevation"] = bundle
    ctrl.data = data
    if disabled:
        ctrl.shadow = None
        ctrl.on_hover = None
        return ctrl
    ctrl.shadow = shadow_from_spec(bundle["rest"])
    ctrl.animate = ft.Animation(120, ft.AnimationCurve.EASE_OUT)

    def _on_hover(e: Any) -> None:
        on = _hover_on(e)
        if on is None:
            return
        ctrl.shadow = shadow_from_spec(bundle["hover"] if on else bundle["rest"])
        try:
            ctrl.update()
        except Exception:  # noqa: BLE001
            pass

    ctrl.on_hover = _on_hover
    return ctrl


def filled_button_style() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={CS.DEFAULT: COLORS["accent"], CS.DISABLED: "#93C5FD"},
        color="#FFFFFF",
        elevation={CS.DEFAULT: 1, CS.HOVERED: 4, CS.PRESSED: 0, CS.DISABLED: 0},
        shadow_color="#0F172A33",
        animation_duration=120,
        padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        shape=ft.RoundedRectangleBorder(radius=10),
    )


def outlined_button_style(*, disabled: bool = False) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        elevation={
            CS.DEFAULT: 0 if disabled else 0,
            CS.HOVERED: 0 if disabled else 3,
            CS.PRESSED: 0,
            CS.DISABLED: 0,
        },
        shadow_color="#0F172A22",
        animation_duration=120,
        padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        shape=ft.RoundedRectangleBorder(radius=10),
        overlay_color={CS.HOVERED: "#0F172A08", CS.DISABLED: "transparent"},
    )


def elevated_filled_button(content: str, *, on_click: Any = None, **kwargs: Any) -> ft.FilledButton:
    kwargs.setdefault("bgcolor", COLORS["accent"])
    kwargs.setdefault("color", "#FFFFFF")
    kwargs.setdefault("style", filled_button_style())
    btn = ft.FilledButton(content=content, on_click=on_click, **kwargs)
    btn.data = {**(btn.data or {}), "elevation": "filled"}
    return btn


def elevated_outlined_button(
    content: str,
    *,
    on_click: Any = None,
    disabled: bool = False,
    **kwargs: Any,
) -> ft.OutlinedButton:
    kwargs.setdefault("style", outlined_button_style(disabled=disabled))
    kwargs.setdefault("disabled", disabled)
    btn = ft.OutlinedButton(content=content, on_click=on_click, **kwargs)
    btn.data = {**(btn.data or {}), "elevation": None if disabled else "outlined"}
    return btn
