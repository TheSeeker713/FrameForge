"""Step 5.1 — shortcut registry contains required action ids."""

from __future__ import annotations

from types import SimpleNamespace

from frameforge.gui.shortcuts import (
    REQUIRED_ACTION_IDS,
    ShortcutRegistry,
    should_ignore_event,
)


def test_registry_contains_required_action_ids():
    reg = ShortcutRegistry()
    ids = set(reg.action_ids())
    missing = [a for a in REQUIRED_ACTION_IDS if a not in ids]
    assert not missing, missing
    assert "quit" in ids
    assert "convert_mp3" in ids
    assert "shortcuts_help" in ids
    assert all(reg.label_for(a) for a in REQUIRED_ACTION_IDS)


def test_plain_keys_ignored_in_entry_without_modifier():
    class CTkEntry:
        pass

    class CTkButton:
        pass

    entry = CTkEntry()
    plain = SimpleNamespace(widget=entry, keysym="d", state=0)
    ctrl = SimpleNamespace(widget=entry, keysym="d", state=0x4)
    f1 = SimpleNamespace(widget=entry, keysym="F1", state=0)
    other = SimpleNamespace(widget=CTkButton(), keysym="d", state=0)
    assert should_ignore_event(plain) is True
    assert should_ignore_event(ctrl) is False
    assert should_ignore_event(f1) is False
    assert should_ignore_event(other) is False
