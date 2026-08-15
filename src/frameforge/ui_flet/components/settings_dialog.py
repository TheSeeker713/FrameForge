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
    delay = ft.TextField(
        label="Inter-job delay (seconds, 0–60)",
        value=str(repo.get_setting("inter_job_delay_sec", "3")),
        width=220,
    )
    rate = ft.TextField(
        label="Max download rate (0 = unlimited, e.g. 2M)",
        value=str(repo.get_setting("max_download_rate", "0")),
        width=280,
    )
    fragments = ft.TextField(
        label="Concurrent fragments (-N, default 8)",
        value=str(repo.get_setting("concurrent_fragments", "8")),
        width=280,
    )
    aria2_n = ft.TextField(
        label="aria2 connections (-x/-s, default 16, max 16)",
        value=str(repo.get_setting("aria2_connections", "16")),
        width=280,
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
    from frameforge.download.js_runtime import js_runtime_status
    from frameforge.download.youtube_clients import DEFAULT_PLAYER_CLIENTS

    innertube = ft.Switch(
        label="YouTube Innertube clients (anonymous public downloads)",
        value=str(repo.get_setting("youtube_innertube", "1") or "1") != "0"
        and str(repo.get_setting("youtube_use_ytdlp_clients", "0") or "0") != "1",
    )
    clients = ft.TextField(
        label="YouTube player_client order",
        value=str(repo.get_setting("youtube_player_clients", DEFAULT_PLAYER_CLIENTS) or DEFAULT_PLAYER_CLIENTS),
        width=420,
    )
    ytdlp_defaults = ft.Switch(
        label="Use yt-dlp default YouTube clients (no extractor-args)",
        value=str(repo.get_setting("youtube_use_ytdlp_clients", "0") or "0") == "1",
    )

    js = js_runtime_status()
    js_tip = ft.Text(
        f"YouTube JS runtime: {js['runtime']} ({js['path']})"
        if js.get("ok")
        else (js.get("tip") or "Deno not found — YouTube n-challenge will fail."),
        color=COLORS["text_secondary"] if js.get("ok") else COLORS["warn"],
        size=12,
    )

    def save(_e=None) -> None:
        repo.set_setting("format_preference", (fmt.value or "Best").strip() or "best")
        repo.set_setting("gentle_rate_mode", "1" if gentle.value else "0")
        raw_delay = str(delay.value or "3").strip() or "3"
        try:
            delay_sec = max(0.0, min(60.0, float(raw_delay)))
        except ValueError:
            delay_sec = 3.0
        repo.set_setting("inter_job_delay_sec", str(int(delay_sec) if delay_sec == int(delay_sec) else delay_sec))
        repo.set_setting("max_download_rate", str(rate.value or "0").strip() or "0")
        from frameforge.download.throughput import (
            DEFAULT_ARIA2_CONNECTIONS,
            DEFAULT_CONCURRENT_FRAGMENTS,
            aria2_connections,
            concurrent_fragments,
        )

        repo.set_setting("concurrent_fragments", str(fragments.value or DEFAULT_CONCURRENT_FRAGMENTS).strip())
        repo.set_setting("aria2_connections", str(aria2_n.value or DEFAULT_ARIA2_CONNECTIONS).strip())
        repo.set_setting("concurrent_fragments", str(concurrent_fragments(repo)))
        repo.set_setting("aria2_connections", str(aria2_connections(repo)))
        repo.set_setting("upscale_after_download", "1" if upscale.value else "0")
        repo.set_setting("close_to_tray", "1" if tray.value else "0")
        repo.set_setting("fail_pause_on_auth", "1" if fail_pause.value else "0")
        repo.set_setting("youtube_innertube", "1" if innertube.value else "0")
        repo.set_setting("youtube_use_ytdlp_clients", "1" if ytdlp_defaults.value else "0")
        repo.set_setting(
            "youtube_player_clients",
            str(clients.value or DEFAULT_PLAYER_CLIENTS).strip() or DEFAULT_PLAYER_CLIENTS,
        )
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
                ft.Text(
                    "Jobs stay sequential. Delay waits before the next pending download.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                delay,
                rate,
                fragments,
                aria2_n,
                innertube,
                ytdlp_defaults,
                clients,
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
                js_tip,
            ),
        ],
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        width=480,
        height=580,
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
        "delay": delay,
        "rate": rate,
        "fragments": fragments,
        "aria2_n": aria2_n,
        "upscale": upscale,
        "tray": tray,
        "fail_pause": fail_pause,
        "save": save,
        "cancel": cancel,
    }
    return dlg
