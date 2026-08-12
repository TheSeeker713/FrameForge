"""Step 4.1 — psutil resource sampler returns numeric CPU/RAM."""

from __future__ import annotations

from frameforge.monitor.sampler import ResourceSampler


def test_sampler_returns_numeric_cpu_ram():
    sampler = ResourceSampler()
    first = sampler.sample()
    assert first.ok is True
    assert isinstance(first.cpu_percent, float)
    assert isinstance(first.ram_percent, float)
    assert 0.0 <= first.ram_percent <= 100.0
    assert first.ram_total_bytes > 0
    # First cpu_percent is primed; a second sample is still numeric and non-crashing
    second = sampler.sample()
    assert second.ok is True
    assert isinstance(second.cpu_percent, float)
    assert 0.0 <= second.cpu_percent <= 100.0
    assert sampler.last is second
