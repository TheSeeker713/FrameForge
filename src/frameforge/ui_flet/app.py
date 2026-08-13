"""Flet desktop shell — light FrameForge window."""

from __future__ import annotations

from typing import Any

import flet as ft

from frameforge.db.repository import JobRepository
from frameforge.paths import db_path, ensure_output_tree
from frameforge.pipeline import build_worker
from frameforge.ui_flet.bridge import UiBridge
from frameforge.ui_flet.components.settings_dialog import build_settings_dialog
from frameforge.ui_flet.components.status_pill import status_from_repo
from frameforge.ui_flet.theme import (
    COLORS,
    FONT_FAMILY,
    TAB_LABELS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)


def apply_page_chrome(page: ft.Page) -> None:
    page.title = "FrameForge"
    page.bgcolor = COLORS["app_bg"]
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.theme = ft.Theme(font_family=FONT_FAMILY, color_scheme_seed=COLORS["accent"])
    window = getattr(page, "window", None)
    if window is not None:
        window.width = WINDOW_WIDTH
        window.height = WINDOW_HEIGHT
        window.min_width = 900
        window.min_height = 600


def _placeholder_panel(label: str) -> ft.Container:
    return ft.Container(
        expand=True,
        bgcolor=COLORS["surface"],
        border=ft.Border.all(1, COLORS["border"]),
        border_radius=12,
        padding=24,
        content=ft.Text(
            f"{label} placeholder",
            color=COLORS["text_secondary"],
            size=14,
        ),
    )


def build_header(
    *,
    status_text: str = "Idle • 0 ready",
    on_settings: Any | None = None,
    on_authenticate: Any | None = None,
) -> ft.Row:
    return ft.Row(
        [
            ft.Text(
                "FrameForge",
                size=22,
                weight=ft.FontWeight.BOLD,
                color=COLORS["text_primary"],
            ),
            ft.Container(expand=True),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor=COLORS["surface"],
                border=ft.Border.all(1, COLORS["border"]),
                border_radius=999,
                content=ft.Text(status_text, color=COLORS["text_secondary"], size=13),
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.SETTINGS_OUTLINED,
                tooltip="Settings",
                icon_color=COLORS["text_primary"],
                on_click=on_settings,
            ),
            ft.IconButton(
                icon=ft.Icons.SHIELD_OUTLINED,
                tooltip="Authenticate",
                icon_color=COLORS["text_primary"],
                on_click=on_authenticate,
            ),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def build_hero(*, on_add: Any | None = None, on_import: Any | None = None) -> ft.Row:
    url = ft.TextField(
        hint_text="Paste video URL or drop link here...",
        expand=True,
        border_color=COLORS["border"],
        focused_border_color=COLORS["accent"],
        prefix_icon=ft.Icons.LINK,
    )
    add = ft.FilledButton(
        content="+ Add to Queue",
        bgcolor=COLORS["accent"],
        color="#FFFFFF",
        on_click=on_add,
    )
    imp = ft.OutlinedButton(content="Import TXT/MD", icon=ft.Icons.UPLOAD_FILE, on_click=on_import)
    row = ft.Row([url, add, imp], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    row.data = {"url": url, "add": add, "import": imp}
    return row


def build_tabs() -> ft.Tabs:
    views = [_placeholder_panel(name) for name in TAB_LABELS]
    return ft.Tabs(
        length=len(TAB_LABELS),
        selected_index=0,
        expand=True,
        content=ft.Column(
            expand=True,
            controls=[
                ft.TabBar(
                    tabs=[ft.Tab(label=name) for name in TAB_LABELS],
                    label_color=COLORS["accent"],
                    unselected_label_color=COLORS["text_secondary"],
                    indicator_color=COLORS["accent"],
                    divider_color=COLORS["border"],
                ),
                ft.TabBarView(expand=True, controls=views),
            ],
        ),
    )


class FrameForgeUi:
    """Flet presentation + UiBridge. Worker is idle until Download / Retry."""

    def __init__(
        self,
        repo: JobRepository | None = None,
        *,
        start_worker: bool = False,
        recover_on_launch: bool = True,
        worker: Any | None = None,
    ) -> None:
        ensure_output_tree()
        self.repo = repo or JobRepository(db_path())
        self.worker = worker or build_worker(self.repo)
        self.bridge = UiBridge(self.repo, self.worker)
        if recover_on_launch:
            self.worker.prepare_idle_launch()
        if start_worker:
            self.worker.request_download_all()
        self.page: ft.Page | None = None
        self.settings_dialog: ft.AlertDialog | None = None
        self.settings_focus_count = 0
        self.auth_open = False
        self.header: ft.Row | None = None
        self.hero: ft.Row | None = None
        self.tabs: ft.Tabs | None = None

    def build(self) -> ft.Column:
        status = status_from_repo(self.repo, self.worker)
        self.header = build_header(
            status_text=status,
            on_settings=lambda _e=None: self.open_settings(),
            on_authenticate=lambda _e=None: self.open_authenticate(),
        )
        self.hero = build_hero(
            on_add=lambda _e=None: self.add_url(),
            on_import=lambda _e=None: self.import_file(),
        )
        self.tabs = build_tabs()
        return ft.Column(
            expand=True,
            spacing=16,
            controls=[self.header, self.hero, self.tabs],
        )

    def add_url(self) -> Any | None:
        field = (self.hero.data or {}).get("url") if self.hero is not None else None
        url = (getattr(field, "value", None) or "").strip()
        if not url:
            return None
        job = self.bridge.enqueue_url(url)
        if field is not None:
            field.value = ""
        if self.page is not None:
            self.page.update()
        return job

    def import_file(self) -> None:
        """Placeholder until Phase E bulk-import modal; enqueue is never auto-started."""
        self._pending_import = True

    def open_authenticate(self) -> None:
        self.auth_open = True
        if self.page is not None:
            self.page.update()

    def open_settings(self) -> ft.AlertDialog:
        if self.bridge.settings_open and self.settings_dialog is not None:
            self.settings_focus_count += 1
            if self.page is not None:
                self.page.show_dialog(self.settings_dialog)
                self.page.update()
            return self.settings_dialog

        def on_close(_e=None) -> None:
            self.bridge.settings_open = False
            if self.page is not None:
                self.page.pop_dialog()
                self.page.update()

        self.settings_dialog = build_settings_dialog(
            self.repo,
            on_close=on_close,
        )
        self.bridge.settings_open = True
        if self.page is not None:
            self.page.show_dialog(self.settings_dialog)
            self.page.update()
        return self.settings_dialog

    def attach_page(self, page: ft.Page) -> None:
        self.page = page
        apply_page_chrome(page)
        page.add(self.build())

    def shutdown(self) -> None:
        try:
            self.worker.stop(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.repo.close()
        except Exception:  # noqa: BLE001
            pass


def build_header_default() -> ft.Row:
    return build_header()


def build_shell() -> ft.Column:
    """Light chrome: header + hero + Queue/History/Thumbnails placeholders (no backend)."""
    return ft.Column(
        expand=True,
        spacing=16,
        controls=[build_header(), build_hero(), build_tabs()],
    )


def create_ui(**kwargs: Any) -> FrameForgeUi:
    kwargs.setdefault("recover_on_launch", True)
    kwargs.setdefault("start_worker", False)
    return FrameForgeUi(**kwargs)


def main(page: ft.Page) -> None:
    ui = create_ui()
    ui.attach_page(page)


def run_gui(**kwargs: Any) -> None:
    ui = create_ui(**kwargs)

    def _main(page: ft.Page) -> None:
        ui.attach_page(page)

    ft.app(_main)
