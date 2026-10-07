"""Stop the Flet desktop client from turning on Windows location.

FrameForge never reads coordinates and never sends them anywhere. The window
process is still the Flet client (file description "Flet"). That client loads
``geolocator_windows_plugin.dll`` at startup and constructs a WinRT
``Geolocator``, which makes Windows show "Location in use" for this PC's
location service. Replacing that plugin with a no-op register function means
the WinRT object is never created.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

_PLUGIN_NAME = "geolocator_windows_plugin.dll"
_BACKUP_NAME = "geolocator_windows_plugin.real.dll"


def stub_plugin_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / _PLUGIN_NAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def flet_client_plugin_dir() -> Path | None:
    """Directory that contains ``flet.exe`` for the cached desktop client."""
    try:
        from flet_desktop import ensure_client_cached
    except Exception:  # noqa: BLE001
        log.exception("Flet desktop client is not importable")
        return None
    cache = Path(ensure_client_cached())
    folder = cache / "flet"
    if (folder / "flet.exe").is_file():
        return folder
    return None


def disable_flet_location_plugin(client_dir: Path | None = None) -> Path | None:
    """Install the no-op geolocator plugin next to ``flet.exe``.

    *client_dir* is the folder that contains ``flet.exe``. When omitted, the
    cached Flet client for this version is used. Safe to call more than once.
    A locked file (app already running) is left as-is until the next launch.
    """
    stub = stub_plugin_path()
    if not stub.is_file():
        log.warning("Location stub missing: %s", stub)
        return None
    folder = Path(client_dir) if client_dir is not None else flet_client_plugin_dir()
    if folder is None:
        return None
    target = folder / _PLUGIN_NAME
    if not target.is_file() and client_dir is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.is_dir():
        return None
    try:
        stub_hash = _sha256(stub)
        if target.is_file() and _sha256(target) == stub_hash:
            return target
        backup = folder / _BACKUP_NAME
        if target.is_file() and not backup.is_file():
            shutil.copy2(target, backup)
        shutil.copy2(stub, target)
    except OSError:
        log.exception("Could not replace %s (restart FrameForge if it is open)", target)
        return target if target.is_file() else None
    return target
