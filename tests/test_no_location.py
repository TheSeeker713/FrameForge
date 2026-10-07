"""Flet's geolocator plugin is replaced with a no-op before the window starts."""

from __future__ import annotations

from pathlib import Path

from frameforge.ui_flet.no_location import disable_flet_location_plugin, stub_plugin_path


def test_stub_replaces_geolocator_plugin(tmp_path: Path):
    stub = stub_plugin_path()
    assert stub.is_file()
    assert stub.stat().st_size < 20_000
    target_dir = tmp_path / "flet"
    target_dir.mkdir()
    plugin = target_dir / "geolocator_windows_plugin.dll"
    plugin.write_bytes(b"real-geolocator-plugin")
    replaced = disable_flet_location_plugin(target_dir)
    assert replaced == plugin
    assert plugin.read_bytes() == stub.read_bytes()
    assert (target_dir / "geolocator_windows_plugin.real.dll").read_bytes() == b"real-geolocator-plugin"
    again = disable_flet_location_plugin(target_dir)
    assert again == plugin
    assert plugin.read_bytes() == stub.read_bytes()
