"""CLI entry: python -m frameforge."""

from __future__ import annotations

import argparse
import json
import sys

from frameforge import __version__
from frameforge.env_check import check_environment
from frameforge.paths import ensure_output_tree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="frameforge", description="FrameForge CLI")
    parser.add_argument("--version", action="store_true", help="Print version")
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Probe dependencies and output directories",
    )
    parser.add_argument("--gui", action="store_true", help="Launch Flet GUI")
    parser.add_argument(
        "--reset-library",
        action="store_true",
        help="Clear Library index and onboarding flags (does not delete media files)",
    )
    parser.add_argument(
        "--reset-queue",
        action="store_true",
        help="Clear queue jobs and the download archive (does not delete videos or cookies)",
    )
    args = parser.parse_args(argv)

    if args.version:
        print(f"frameforge {__version__}")
        return 0

    if args.check_env:
        ensure_output_tree()
        report = check_environment()
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    if args.reset_queue:
        from frameforge.db.repository import JobRepository
        from frameforge.paths import db_path
        from frameforge.queue.reset import QueueResetRefused, reset_queue

        path = db_path()
        if not path.is_file():
            print(f"No queue database at {path}")
            return 1
        repo = JobRepository(path)
        try:
            removed = reset_queue(repo)
        except QueueResetRefused as exc:
            print(str(exc))
            return 1
        finally:
            repo.close()
        print(f"Removed {removed} queue jobs. Videos, cookies, and the app home were left in place.")
        return 0

    if args.reset_library:
        from frameforge.db.repository import JobRepository
        from frameforge.library.reset import reset_library_state
        from frameforge.library.store import LibraryStore
        from frameforge.paths import db_path, download_scan_roots

        ensure_output_tree()
        repo = JobRepository(db_path())
        store = LibraryStore(repo)
        reset_library_state(store, download_roots=download_scan_roots())
        repo.close()
        print("Library index and onboarding flags cleared. Media files were not deleted.")
        return 0

    if args.gui:
        from frameforge.ui_flet.app import run_gui

        run_gui()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
