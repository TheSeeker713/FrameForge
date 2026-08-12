"""Windows system tray icon (pystray), detached from the CustomTkinter mainloop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PIL import Image, ImageDraw


def default_tray_image(size: int = 64) -> Image.Image:
    """Simple FrameForge mark so we do not depend on a packaged .ico."""
    img = Image.new("RGBA", (size, size), (20, 28, 40, 255))
    draw = ImageDraw.Draw(img)
    pad = max(4, size // 8)
    draw.rounded_rectangle(
        (pad, pad, size - pad - 1, size - pad - 1),
        radius=max(4, size // 6),
        outline=(90, 180, 255, 255),
        width=max(2, size // 16),
    )
    inner = pad * 2
    draw.rectangle(
        (inner, inner, size - inner - 1, size - inner - 1),
        fill=(90, 180, 255, 255),
    )
    return img


class TrayService:
    """Create/stop a pystray icon. UI callbacks must be marshaled onto Tk."""

    def __init__(
        self,
        *,
        widget: Any | None = None,
        on_show: Callable[[], None] | None = None,
        on_pause_resume: Callable[[], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        pause_resume_label: Callable[[], str] | None = None,
        icon_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.widget = widget
        self.on_show = on_show
        self.on_pause_resume = on_pause_resume
        self.on_quit = on_quit
        self.pause_resume_label = pause_resume_label
        self._icon_factory = icon_factory
        self._icon: Any | None = None
        self._started = False

    @property
    def is_running(self) -> bool:
        return bool(self._started and self._icon is not None)

    def marshal(self, fn: Callable[[], None] | None) -> None:
        if fn is None:
            return
        widget = self.widget
        after = getattr(widget, "after", None) if widget is not None else None
        if callable(after):
            after(0, fn)
            return
        fn()

    def _menu(self) -> Any:
        import pystray

        def item(text: str, callback: Callable[[], None] | None) -> Any:
            return pystray.MenuItem(text, lambda *_a: self.marshal(callback))

        pause_text = "Pause current / Resume current"
        if self.pause_resume_label:
            try:
                pause_text = self.pause_resume_label()
            except Exception:  # noqa: BLE001
                pass
        return pystray.Menu(
            item("Show window", self.on_show),
            item(pause_text, self.on_pause_resume),
            item("Quit", self.on_quit),
        )

    def start(self) -> None:
        if self._started:
            return
        factory = self._icon_factory
        if factory is None:
            import pystray

            factory = pystray.Icon
        menu = self._menu()
        self._icon = factory("FrameForge", default_tray_image(), "FrameForge", menu)
        run_det = getattr(self._icon, "run_detached", None)
        if callable(run_det):
            run_det()
        else:
            run = getattr(self._icon, "run", None)
            if callable(run):
                run()
        self._started = True

    def stop(self, timeout: float = 5.0) -> None:
        icon = self._icon
        self._started = False
        self._icon = None
        if icon is None:
            return
        stop = getattr(icon, "stop", None)
        if callable(stop):
            stop()
        join = getattr(icon, "join", None)
        if callable(join):
            try:
                join(timeout)
            except TypeError:
                join()

    def update_menu(self) -> None:
        icon = self._icon
        if icon is None:
            return
        updater = getattr(icon, "update_menu", None)
        if callable(updater):
            icon.menu = self._menu()
            updater()
