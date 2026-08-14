"""PyInstaller runtime hook: point Flet at the bundled Windows client."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _set_flet_view() -> None:
    if not getattr(sys, "frozen", False):
        return
    base = Path(sys.executable).resolve().parent
    meipass = Path(getattr(sys, "_MEIPASS", base))
    for view in (base / "flet-client", meipass / "flet-client", base / "_internal" / "flet-client"):
        if (view / "flet.exe").is_file():
            os.environ.setdefault("FLET_VIEW_PATH", str(view))
            return


_set_flet_view()
