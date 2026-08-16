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
    args = parser.parse_args(argv)

    if args.version:
        print(f"frameforge {__version__}")
        return 0

    if args.check_env:
        ensure_output_tree()
        report = check_environment()
        print(json.dumps(report, indent=2))
        return 0 if report.get("ok") else 1

    if args.reset_library:
        from frameforge.db.repository import JobRepository
        from frameforge.library.reset import reset_library_state
        from frameforge.library.store import LibraryStore
        from frameforge.paths import db_path, frameforge_root

        ensure_output_tree()
        repo = JobRepository(db_path())
        store = LibraryStore(repo)
        reset_library_state(store, download_roots=[frameforge_root()])
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
