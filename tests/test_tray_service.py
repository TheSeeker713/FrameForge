"""Step 3.1 — pystray tray service start/stop without hanging the suite."""

from __future__ import annotations

import time

from frameforge.gui.tray import TrayService, default_tray_image


class _FakeIcon:
    def __init__(self, name, image, title, menu) -> None:
        self.name = name
        self.image = image
        self.title = title
        self.menu = menu
        self.stopped = False
        self.detached = False

    def run_detached(self) -> None:
        self.detached = True

    def stop(self) -> None:
        self.stopped = True

    def update_menu(self) -> None:
        pass


def test_default_tray_image():
    img = default_tray_image(32)
    assert img.size == (32, 32)


def test_tray_service_start_stop_detached():
    marshaled: list[str] = []

    class Widget:
        def after(self, _ms: int, fn) -> None:
            fn()
            marshaled.append("after")

    svc = TrayService(
        widget=Widget(),
        on_show=lambda: marshaled.append("show"),
        on_quit=lambda: marshaled.append("quit"),
        icon_factory=_FakeIcon,
    )
    svc.start()
    assert svc.is_running
    assert isinstance(svc._icon, _FakeIcon)
    assert svc._icon.detached is True
    svc.marshal(svc.on_show)
    assert "show" in marshaled
    svc.stop(timeout=1)
    assert svc._icon is None
    assert not svc.is_running


def test_tray_real_pystray_start_stop():
    """Real pystray detached run; must return quickly."""
    import pystray

    svc = TrayService(icon_factory=pystray.Icon)
    t0 = time.time()
    svc.start()
    assert svc.is_running
    time.sleep(0.2)
    svc.stop(timeout=5)
    assert not svc.is_running
    assert time.time() - t0 < 8
