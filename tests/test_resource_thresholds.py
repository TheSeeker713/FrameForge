"""Step 4.2 — sustained resource thresholds produce a warning flag."""

from __future__ import annotations

from frameforge.monitor.policy import MonitorSettings, ResourceMonitor
from frameforge.monitor.sampler import ResourceReading


def _reading(cpu: float, ram: float) -> ResourceReading:
    return ResourceReading(
        cpu_percent=cpu,
        ram_percent=ram,
        ram_used_bytes=1,
        ram_total_bytes=2,
        ok=True,
    )


def test_inject_high_readings_sets_warning():
    mon = ResourceMonitor(
        MonitorSettings(
            enabled=True,
            ram_warning_pct=90.0,
            cpu_warning_pct=95.0,
            sustained_seconds=3.0,
        )
    )
    t0 = 1000.0
    assert mon.ingest(_reading(10, 50), now=t0).warning is False
    assert mon.ingest(_reading(10, 95), now=t0 + 1).warning is False
    state = mon.ingest(_reading(10, 96), now=t0 + 4.0)
    assert state.warning is True
    assert state.critical is True
    assert "RAM" in (state.reason or "")


def test_spike_below_sustained_is_not_warning():
    mon = ResourceMonitor(MonitorSettings(sustained_seconds=8.0, ram_warning_pct=90))
    t0 = 0.0
    mon.ingest(_reading(99, 99), now=t0)
    assert mon.ingest(_reading(5, 10), now=t0 + 1).warning is False


def test_resource_banner_shows_injected_warning(tmp_path):
    import pytest

    from frameforge.db.repository import JobRepository
    from tests.test_tray_service import _FakeIcon

    try:
        from frameforge.gui.app import FrameForgeApp
    except Exception as exc:
        pytest.skip(f"Tk unavailable: {exc}")

    repo = JobRepository(tmp_path / "r.db")
    try:
        app = FrameForgeApp(repo=repo, start_worker=False, tray_icon_factory=_FakeIcon)
    except Exception as exc:
        repo.close()
        pytest.skip(f"Tk unavailable: {exc}")
    app.withdraw()
    try:
        app.resource_monitor.state.warning = True
        app.resource_monitor.state.reason = "resource_pressure: RAM 95%"
        app._apply_resource_banner()
        assert "RAM 95" in app.resource_banner.cget("text")
    finally:
        app._shutting_down = True
        try:
            app.destroy()
        except Exception:
            pass
        repo.close()
