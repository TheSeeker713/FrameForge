"""CPU/RAM resource sampling for upscale warnings (psutil)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ResourceReading:
    cpu_percent: float
    ram_percent: float
    ram_used_bytes: int
    ram_total_bytes: int
    ok: bool = True
    error: str | None = None


class ResourceSampler:
    """Non-fatal CPU/RAM sampler. First cpu_percent call is treated as a baseline."""

    def __init__(self) -> None:
        self._cpu_primed = False
        self.last: ResourceReading | None = None

    def sample(self) -> ResourceReading:
        try:
            import psutil

            if not self._cpu_primed:
                psutil.cpu_percent(interval=None)
                self._cpu_primed = True
            cpu = float(psutil.cpu_percent(interval=None))
            mem = psutil.virtual_memory()
            reading = ResourceReading(
                cpu_percent=cpu,
                ram_percent=float(mem.percent),
                ram_used_bytes=int(mem.used),
                ram_total_bytes=int(mem.total),
                ok=True,
            )
        except Exception as exc:  # noqa: BLE001
            reading = ResourceReading(
                cpu_percent=0.0,
                ram_percent=0.0,
                ram_used_bytes=0,
                ram_total_bytes=0,
                ok=False,
                error=str(exc),
            )
        self.last = reading
        return reading

    def last_or_sample(self) -> ResourceReading:
        return self.last if self.last is not None else self.sample()


def reading_as_dict(reading: ResourceReading) -> dict[str, Any]:
    return {
        "cpu_percent": reading.cpu_percent,
        "ram_percent": reading.ram_percent,
        "ram_used_bytes": reading.ram_used_bytes,
        "ram_total_bytes": reading.ram_total_bytes,
        "ok": reading.ok,
        "error": reading.error,
    }
