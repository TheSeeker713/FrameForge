"""v0.5.8 — hard_exit actually terminates the Python process."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hard_exit_process_returns():
    script = (
        "import sys; sys.path.insert(0, r'%s'); "
        "from frameforge.util.process_tree import hard_exit; "
        "hard_exit(0)"
    ) % str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    assert proc.returncode == 0


def test_schedule_hard_exit_beats_sleep():
    script = (
        "import sys, time; sys.path.insert(0, r'%s'); "
        "from frameforge.util.process_tree import schedule_hard_exit; "
        "schedule_hard_exit(0.2, 0); "
        "time.sleep(30); "
        "raise SystemExit(7)"
    ) % str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    assert proc.returncode == 0
