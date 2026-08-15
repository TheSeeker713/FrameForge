"""In-memory undo for queue/history soft-hide. Never restores deleted media (media is never deleted)."""

from __future__ import annotations

from dataclasses import dataclass

MAX_UNDO = 5


@dataclass(frozen=True)
class HideSnapshot:
    job_id: int
    queue_hidden: bool
    history_hidden: bool


@dataclass
class ClearUndoEntry:
    kind: str
    snapshots: list[HideSnapshot]

    @property
    def count(self) -> int:
        return len(self.snapshots)

    @property
    def message(self) -> str:
        n = self.count
        noun = "item" if n == 1 else "items"
        return f"Cleared {n} {noun} — Undo"


class ClearUndoStack:
    def __init__(self, maxlen: int = MAX_UNDO) -> None:
        self.maxlen = maxlen
        self.entries: list[ClearUndoEntry] = []

    def push(self, entry: ClearUndoEntry) -> None:
        self.entries.append(entry)
        extra = len(self.entries) - self.maxlen
        if extra > 0:
            del self.entries[:extra]

    def pop(self) -> ClearUndoEntry | None:
        return self.entries.pop() if self.entries else None

    def peek(self) -> ClearUndoEntry | None:
        return self.entries[-1] if self.entries else None

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __len__(self) -> int:
        return len(self.entries)
