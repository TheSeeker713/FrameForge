"""Sustained CPU/RAM warning policy for upscale monitoring."""

from __future__ import annotations

import time
from dataclasses import dataclass

from frameforge.monitor.sampler import ResourceReading

DEFAULT_RAM_WARNING_PCT = 90.0
DEFAULT_CPU_WARNING_PCT = 95.0
DEFAULT_SUSTAINED_SECONDS = 8.0
PAUSE_REASON = "resource_pressure"


@dataclass
class MonitorSettings:
    enabled: bool = True
    ram_warning_pct: float = DEFAULT_RAM_WARNING_PCT
    cpu_warning_pct: float = DEFAULT_CPU_WARNING_PCT
    sustained_seconds: float = DEFAULT_SUSTAINED_SECONDS
    auto_pause: bool = False


@dataclass
class MonitorState:
    warning: bool = False
    critical: bool = False
    reason: str | None = None
    cpu_percent: float = 0.0
    ram_percent: float = 0.0


def settings_from_repo(repo: object) -> MonitorSettings:
    get = getattr(repo, "get_setting", None)
    if get is None:
        return MonitorSettings()

    def _bool(key: str, default: str) -> bool:
        return str(get(key, default) or default).strip() in {"1", "true", "yes", "on"}

    def _float(key: str, default: float) -> float:
        try:
            return float(get(key, str(default)) or default)
        except (TypeError, ValueError):
            return default

    return MonitorSettings(
        enabled=_bool("resource_monitor_enabled", "1"),
        ram_warning_pct=_float("ram_warning_pct", DEFAULT_RAM_WARNING_PCT),
        cpu_warning_pct=_float("cpu_warning_pct", DEFAULT_CPU_WARNING_PCT),
        sustained_seconds=_float("resource_sustained_seconds", DEFAULT_SUSTAINED_SECONDS),
        auto_pause=_bool("resource_auto_pause", "0"),
    )


def save_settings_to_repo(repo: object, settings: MonitorSettings) -> None:
    repo.set_setting("resource_monitor_enabled", "1" if settings.enabled else "0")
    repo.set_setting("ram_warning_pct", str(settings.ram_warning_pct))
    repo.set_setting("cpu_warning_pct", str(settings.cpu_warning_pct))
    repo.set_setting("resource_sustained_seconds", str(settings.sustained_seconds))
    repo.set_setting("resource_auto_pause", "1" if settings.auto_pause else "0")


class ResourceMonitor:
    """Tracks sustained high CPU/RAM. Monitoring failures are non-fatal."""

    def __init__(self, settings: MonitorSettings | None = None) -> None:
        self.settings = settings or MonitorSettings()
        self.state = MonitorState()
        self._high_since: float | None = None

    def ingest(self, reading: ResourceReading, *, now: float | None = None) -> MonitorState:
        now = time.monotonic() if now is None else now
        self.state.cpu_percent = reading.cpu_percent
        self.state.ram_percent = reading.ram_percent
        if not self.settings.enabled or not reading.ok:
            self._high_since = None
            self.state.warning = False
            self.state.critical = False
            self.state.reason = None
            return self.state
        ram_high = reading.ram_percent >= self.settings.ram_warning_pct
        cpu_high = reading.cpu_percent >= self.settings.cpu_warning_pct
        if ram_high or cpu_high:
            if self._high_since is None:
                self._high_since = now
            elapsed = now - self._high_since
            if elapsed >= self.settings.sustained_seconds:
                self.state.warning = True
                self.state.critical = ram_high
                parts = []
                if ram_high:
                    parts.append(f"RAM {reading.ram_percent:.0f}%")
                if cpu_high:
                    parts.append(f"CPU {reading.cpu_percent:.0f}%")
                self.state.reason = "resource_pressure: " + ", ".join(parts)
            else:
                self.state.warning = False
                self.state.critical = False
                self.state.reason = None
        else:
            self._high_since = None
            self.state.warning = False
            self.state.critical = False
            self.state.reason = None
        return self.state


def maybe_auto_pause_upscale(worker: object, monitor: ResourceMonitor) -> bool:
    """Pause the active upscale when auto-pause is on and RAM pressure is critical."""
    if not monitor.settings.auto_pause or not monitor.state.critical:
        return False
    repo = getattr(worker, "repo", None)
    if repo is None:
        return False
    pause_job = getattr(worker, "pause_job", None)
    for job in list(repo.list_jobs("upscaling")):
        if pause_job is not None:
            pause_job(job.id)
        else:
            repo.pause(job.id)
        repo.merge_options(job.id, {"pause_reason": PAUSE_REASON})
        return True
    return False
