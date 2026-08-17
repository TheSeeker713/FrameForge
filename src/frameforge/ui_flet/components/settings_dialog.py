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
    on_open_cookies: Any | None = None,
    library: Any | None = None,
    on_pick_library_root: Any | None = None,
    on_pick_watch_folder: Any | None = None,
    on_set_private_password: Any | None = None,
    on_reset_library: Any | None = None,
    on_repair_folders: Any | None = None,
    repair_status: Any | None = None,
    repair_button: Any | None = None,
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
    upscale_max_min = ft.TextField(
        label="Max upscale duration (minutes)",
        value=str(repo.get_setting("upscale_max_duration_min", "15") or "15"),
        width=220,
    )
    keep_frames = ft.Switch(
        label="Keep upscale PNG frames (debug)",
        value=str(repo.get_setting("upscale_keep_frames", "0") or "0") == "1",
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
    from frameforge.download.impersonate import (
        DEFAULT_AUTO_HOSTS,
        DEFAULT_MODE as IMPERSONATE_DEFAULT,
        HOSTS_SETTING,
        MODE_ALWAYS,
        MODE_AUTO,
        MODE_OFF,
        impersonate_mode,
        impersonation_status,
    )

    _imp_labels = {
        MODE_AUTO: "Auto (listed hosts)",
        MODE_ALWAYS: "Always",
        MODE_OFF: "Off",
    }
    _imp_from_label = {v: k for k, v in _imp_labels.items()}
    impersonate_dd = ft.Dropdown(
        label="Browser impersonate (--impersonate)",
        value=_imp_labels.get(impersonate_mode(repo), _imp_labels[IMPERSONATE_DEFAULT]),
        options=[ft.dropdown.Option(lab) for lab in _imp_labels.values()],
        width=320,
    )
    imp_st = impersonation_status()
    impersonate_tip = ft.Text(
        (
            f"Chrome impersonate available (curl_cffi {imp_st.get('curl_cffi_version')}; "
            f"selected {imp_st.get('selected')})"
            if imp_st.get("ok")
            else (imp_st.get("error") or "Chrome impersonate unavailable — run --check-env.")
        ),
        color=COLORS["text_secondary"] if imp_st.get("ok") else COLORS["warn"],
        size=12,
    )
    impersonate_hosts = ft.TextField(
        label="Auto impersonate hosts (comma-separated)",
        value=str(repo.get_setting(HOSTS_SETTING, "") or "") or ",".join(DEFAULT_AUTO_HOSTS),
        width=420,
    )
    silent_cookies = ft.Switch(
        label="Silent Firefox/Edge cookie import on auth/bot (one retry, never Chrome)",
        value=str(repo.get_setting("silent_browser_cookies", "1") or "1") != "0",
    )

    js = js_runtime_status()
    js_tip = ft.Text(
        f"YouTube JS runtime: {js['runtime']} ({js['path']})"
        if js.get("ok")
        else (js.get("tip") or "Deno not found — YouTube n-challenge will fail."),
        color=COLORS["text_secondary"] if js.get("ok") else COLORS["warn"],
        size=12,
    )
    from frameforge.download.cookies import cookie_store_status

    store = cookie_store_status()
    cookies_path = ft.Text(
        f"Cookies folder: {store['directory']}",
        color=COLORS["text_secondary"],
        size=12,
        selectable=True,
    )
    cookies_list = ft.Text(
        f"Domain files: {store['label']}",
        color=COLORS["text_secondary"],
        size=12,
        selectable=True,
    )

    def _open_cookies(_e=None) -> None:
        if on_open_cookies:
            on_open_cookies()

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
        repo.set_setting(
            "impersonate_mode",
            _imp_from_label.get(str(impersonate_dd.value or ""), IMPERSONATE_DEFAULT),
        )
        raw_hosts = str(impersonate_hosts.value or "").strip()
        repo.set_setting(HOSTS_SETTING, raw_hosts)
        repo.set_setting("silent_browser_cookies", "1" if silent_cookies.value else "0")
        if ram.value:
            repo.set_setting("ram_warning_pct", str(ram.value).strip())
        raw_upscale_min = str(upscale_max_min.value or "15").strip() or "15"
        try:
            upscale_min = max(0.0, min(24 * 60, float(raw_upscale_min)))
        except ValueError:
            upscale_min = 15.0
        repo.set_setting("upscale_max_duration_min", str(upscale_min))
        repo.set_setting("upscale_keep_frames", "1" if keep_frames.value else "0")
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
                impersonate_dd,
                impersonate_hosts,
                silent_cookies,
                impersonate_tip,
            ),
            _card(
                "Cookies",
                cookies_path,
                cookies_list,
                ft.OutlinedButton(content="Open cookies folder", on_click=_open_cookies),
            ),
            _card(
                "AI and Upscaling",
                upscale,
                ft.Text(
                    "PNG-pipeline disk guard: refuse if temp frames would fill the drive. "
                    "Duration cap (default 15 min) until streaming upscale ships. See docs/UPSCALE_DISK.md.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                upscale_max_min,
                keep_frames,
                ft.Text("Pause AI tasks under RAM pressure.", color=COLORS["text_secondary"], size=12),
                ram,
            ),
            _card(
                "Library (local only)",
                ft.Text(
                    "Changing the library root does not move files automatically. Re-index extra folders after you confirm.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                ft.Text(
                    f"Library folder: {library.root() if library and library.root() else 'not set'}",
                    selectable=True,
                    size=12,
                    color=COLORS["text_primary"],
                ),
                ft.OutlinedButton(
                    content="Change library folder…",
                    on_click=lambda _e: on_pick_library_root and on_pick_library_root(),
                ),
                ft.OutlinedButton(
                    content="Add extra folder (index)…",
                    on_click=lambda _e: on_pick_watch_folder and on_pick_watch_folder(),
                ),
            ),
            _card(
                "Private",
                ft.Text(
                    "Password-gated copies in a zip. Extension disguise hides from casual browsing. "
                    "Not remote security. Forgotten password cannot be recovered by email.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                ft.OutlinedButton(
                    content="Set / change Private password",
                    on_click=lambda _e: on_set_private_password and on_set_private_password(),
                ),
            ),
            _card(
                "Folders",
                ft.Text(
                    "Keep per-site download folders. Move thumbs next to videos into thumbnails/, "
                    "leftover .part/.aria2/.ytdl into temp/junk/, info.json into metadata/. "
                    "Never Recycles without you. Runs in the background.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                repair_status
                or ft.Text("", size=12, color=COLORS["text_secondary"]),
                repair_button
                or ft.OutlinedButton(
                    content="Repair folders",
                    on_click=lambda _e: on_repair_folders and on_repair_folders(),
                ),
            ),
            _card(
                "Advanced",
                ft.Text(
                    "Reset Library onboarding to retest first-run. Index and flags are cleared; "
                    "media files stay on disk. Same as scripts/reset_library.ps1 and reset_library_state.ps1.",
                    color=COLORS["text_secondary"],
                    size=12,
                ),
                ft.OutlinedButton(
                    content="Reset Library onboarding…",
                    on_click=lambda _e: on_reset_library and on_reset_library(),
                ),
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
        height=720,
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
        "impersonate": impersonate_dd,
        "save": save,
        "cancel": cancel,
        "cookies_path": cookies_path,
        "cookies_list": cookies_list,
        "cookies_dir": store["directory"],
        "cookie_files": store["label"],
        "on_open_cookies": on_open_cookies,
    }
    return dlg
