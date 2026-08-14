"""Settings dialog — three cards, one open instance."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.download.formats import PRESET_LABELS, label_for_preference
from frameforge.ui_flet.elevation import elevated_filled_button, elevated_outlined_button
from frameforge.ui_flet.theme import COLORS, RADIUS_CARD


def _card(title: str, *body: ft.Control) -> ft.Container:
    return ft.Container(
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=RADIUS_CARD,
        padding=16,
        content=ft.Column(
            [ft.Text(title, weight=ft.FontWeight.BOLD, color=COLORS["text_primary"], size=15), *body],
            spacing=8,
        ),
    )


def build_settings_dialog(
    repo: Any,
    *,
    on_save: Any | None = None,
    on_close: Any | None = None,
) -> ft.AlertDialog:
    fmt_value = label_for_preference(repo.get_setting("format_preference", "best"))
    fmt = ft.Dropdown(
        value=fmt_value,
        options=[ft.dropdown.Option(label) for label in PRESET_LABELS],
        width=280,
    )
    gentle = ft.Switch(
        label="Gentle rate (sleep + 2 MiB/s cap after bot-check)",
        value=repo.get_setting("gentle_rate_mode", "0") == "1",
    )
    upscale = ft.Checkbox(
        label="Enable AI upscaling after download (still sequential)",
        value=repo.get_setting("upscale_after_download", "0") == "1",
    )
    ram = ft.TextField(
        label="RAM warning %",
        value=repo.get_setting("ram_warning_pct", "90"),
        width=160,
    )
    tray = ft.Switch(
        label="Close to system tray",
        value=repo.get_setting("close_to_tray", "0") == "1",
    )
    fail_pause = ft.Switch(
        label="Pause queue on bot-check / login failures",
        value=repo.get_setting("fail_pause_on_auth", "1") == "1",
    )

    def save(_e=None) -> None:
        repo.set_setting("format_preference", (fmt.value or "Best").strip() or "best")
        repo.set_setting("gentle_rate_mode", "1" if gentle.value else "0")
        repo.set_setting("upscale_after_download", "1" if upscale.value else "0")
        repo.set_setting("close_to_tray", "1" if tray.value else "0")
        repo.set_setting("fail_pause_on_auth", "1" if fail_pause.value else "0")
        if ram.value:
            repo.set_setting("ram_warning_pct", str(ram.value).strip())
        if on_save:
            on_save()
        if on_close:
            on_close()

    def cancel(_e=None) -> None:
        if on_close:
            on_close()

    body = ft.Column(
        [
            _card(
                "Download and Quality",
                ft.Text("Preferred download file format.", color=COLORS["text_secondary"], size=12),
                fmt,
                gentle,
            ),
            _card(
                "AI and Upscaling",
                upscale,
                ft.Text("Pause AI tasks under RAM pressure.", color=COLORS["text_secondary"], size=12),
                ram,
            ),
            _card(
                "System Behavior",
                tray,
                fail_pause,
            ),
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        width=480,
        height=420,
    )
    dlg = ft.AlertDialog(
        modal=False,
        title=ft.Text("Settings", color=COLORS["text_primary"], weight=ft.FontWeight.BOLD),
        content=body,
        actions=[
            elevated_outlined_button("Cancel", on_click=cancel),
            elevated_filled_button("Save", on_click=save),
        ],
        bgcolor=COLORS["surface"],
        on_dismiss=cancel,
    )
    dlg.data = {
        "fmt": fmt,
        "gentle": gentle,
        "upscale": upscale,
        "tray": tray,
        "fail_pause": fail_pause,
        "save": save,
        "cancel": cancel,
    }
    return dlg
