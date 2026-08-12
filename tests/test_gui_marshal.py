"""C4 — GUI mutations from worker/tray must marshal onto the Tk thread."""

from __future__ import annotations

from frameforge.gui.marshal import schedule_on_ui


def test_schedule_on_ui_uses_after_zero():
    seen: list[tuple[int, object]] = []

    class Widget:
        def after(self, ms: int, fn):
            seen.append((ms, fn))
            return "id"

    def cb() -> None:
        seen.append((-1, "ran"))

    schedule_on_ui(Widget(), cb)
    assert seen == [(0, cb)]


def test_schedule_on_ui_inline_without_after():
    ran: list[str] = []
    schedule_on_ui(None, lambda: ran.append("ok"))
    assert ran == ["ok"]


def test_schedule_on_ui_inline_when_after_raises():
    ran: list[str] = []

    class Broken:
        def after(self, _ms: int, _fn) -> None:
            raise RuntimeError("destroyed")

    schedule_on_ui(Broken(), lambda: ran.append("ok"))
    assert ran == ["ok"]
