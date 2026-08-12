"""D2 — resource monitor samples without a full queue rebuild."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from frameforge.db.repository import JobRepository
from frameforge.monitor.sampler import ResourceSampler
from tests.test_tray_service import _FakeIcon


def test_sampler_still_numeric():
    sampler = ResourceSampler()
    reading = sampler.sample()
    assert reading.ok is True
    assert 0.0 <= reading.ram_percent <= 100.0


def test_poll_resources_does_not_refresh_queue(tmp_path: Path):
    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "m.db")
    job = repo.enqueue("https://example.com/u", title="u")
    repo.update_status(job.id, "upscaling", progress=10)
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        calls: list[str] = []
        app.refresh_queue = lambda **_k: calls.append("full")  # type: ignore[method-assign]
        app._settings_reload_at = time.monotonic()
        setting_reads = {"n": 0}
        orig = repo.get_setting

        def spy_get(key: str, default: str | None = None) -> str | None:
            setting_reads["n"] += 1
            return orig(key, default)

        repo.get_setting = spy_get  # type: ignore[method-assign]
        app._poll_resources()
        assert calls == []
        assert setting_reads["n"] == 0
        app.resource_monitor.state.warning = True
        app.resource_monitor.state.reason = "RAM 95%"
        app._last_banner_text = None
        configures: list[dict] = []
        orig_cfg = app.resource_banner.configure

        def spy_cfg(*_a, **kw):
            configures.append(kw)
            return orig_cfg(*_a, **kw)

        app.resource_banner.configure = spy_cfg  # type: ignore[method-assign]
        app._apply_resource_banner()
        app._apply_resource_banner()
        assert len(configures) == 1
        assert "RAM 95" in (configures[0].get("text") or "")
    finally:
        app._shutting_down = True
        app._cancel_tick()
        try:
            app.destroy()
        except Exception:  # noqa: BLE001
            pass
        repo.close()
