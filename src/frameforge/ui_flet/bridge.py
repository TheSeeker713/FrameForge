"""Toolkit-free command bridge: Flet (and tests) call these handlers, never the worker loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from frameforge.db.repository import TERMINAL_STATUSES
from frameforge.queue.clear_undo import ClearUndoEntry, ClearUndoStack, HideSnapshot
from frameforge.queue.fail_pause import fail_pause_payload, maybe_fail_pause

AskRetry = Callable[[], bool]
AuthFn = Callable[[str | None], Any]
ImportBrowserFn = Callable[[str], Any]


class UiBridge:
    """Presentation-agnostic commands. Enqueue never arms. Retry uses the same path as the modal."""

    def __init__(self, repo: Any, worker: Any) -> None:
        self.repo = repo
        self.worker = worker
        self.settings_open = False
        self.fail_pause_events: list[dict[str, Any]] = []
        self._on_fail_pause_ui: Callable[[Any, dict[str, Any]], None] | None = None
        self.clear_undo = ClearUndoStack()
        self.last_clear_message: str | None = None
        if getattr(worker, "on_fail_pause", None) is None:
            worker.on_fail_pause = self._dispatch_fail_pause

    def set_fail_pause_handler(self, fn: Callable[[Any, dict[str, Any]], None] | None) -> None:
        self._on_fail_pause_ui = fn
        self.worker.on_fail_pause = self._dispatch_fail_pause

    def _dispatch_fail_pause(self, job: Any) -> None:
        payload = fail_pause_payload(job)
        self.fail_pause_events.append(payload)
        if self._on_fail_pause_ui is not None:
            self._on_fail_pause_ui(job, payload)

    def enqueue_url(self, url: str, **kwargs: Any) -> Any:
        """Add a pending job. Does not start the worker."""
        if not kwargs.get("extractor"):
            from frameforge.download.metadata import site_label_from_url

            kwargs["extractor"] = site_label_from_url(url)
        return self.repo.enqueue(url, **kwargs)

    def retry_job(self, job_id: int) -> None:
        """Reset one failed/cancelled job to pending and arm download for that id (fail-pause Retry)."""
        self.retry_failed_ids([int(job_id)], arm=True)

    def queue_again(self, job_ids: list[int]) -> list[int]:
        """cancelled/failed → pending. Does not start the worker."""
        ids: list[int] = []
        for raw in job_ids:
            job = self.repo.get(int(raw))
            if job.status not in ("failed", "cancelled"):
                continue
            keep = job.progress if job.status == "cancelled" else 0.0
            extra: dict[str, Any] = {"fail_pause": False, "queue_hidden": False}
            opts = job.options()
            if opts.get("error_category") == "output_missing" or opts.get("archive_hit"):
                extra["force_redownload"] = True
                extra["ignore_download_archive"] = True
            self.repo.update_status(job.id, "pending", error=None, progress=keep)
            self.repo.merge_options(job.id, extra)
            ids.append(job.id)
        return ids

    def retry_failed_ids(self, job_ids: list[int], *, arm: bool = True) -> list[int]:
        """Reset given failed/cancelled jobs to pending; optionally arm those ids."""
        ids = self.queue_again(job_ids)
        if arm and ids:
            self.worker.request_download_ids(ids)
        return ids

    def retry_all_failed(self) -> list[int]:
        return self.retry_failed_ids([j.id for j in self.repo.list_jobs("failed")])

    def retry_and_resume(self, job_id: int) -> None:
        """Reset the failed job and arm the whole pending queue (explicit user action)."""
        self.retry_job(int(job_id))
        self.worker.request_download_all()

    def enable_gentle_after_bot(self, n: int | None = None) -> int:
        from frameforge.download.cookie_validate import GENTLE_AFTER_BOT_JOBS, enable_gentle_after_bot

        return enable_gentle_after_bot(self.repo, GENTLE_AFTER_BOT_JOBS if n is None else n)

    def validate_site_cookies(self, url: str, *, probe: Any | None = None) -> Any:
        from frameforge.download.cookie_validate import validate_cookies_for_url

        return validate_cookies_for_url(url, probe=probe if probe is not None else getattr(self, "cookie_probe", None))

    def recover_bot_cookies(
        self,
        url: str,
        *,
        import_browser: ImportBrowserFn | None = None,
        probe: Any | None = None,
    ) -> dict[str, Any]:
        """Import cookies then validate. Never arms the worker. Same core as silent auto recovery."""
        from frameforge.download.recovery import recover_browser_cookies

        if import_browser is None:
            return recover_browser_cookies(url, probe=probe, repo=self.repo)
        return recover_browser_cookies(
            url,
            importer=import_browser,
            probe=probe if probe is not None else getattr(self, "cookie_probe", None),
            repo=self.repo,
        )

    def download_selected(self, job_ids: list[int]) -> None:
        pending = [i for i in job_ids if self.repo.get(i).status == "pending"]
        if pending:
            self.worker.request_download_ids(pending)

    def download_all_pending(self) -> None:
        self.worker.request_download_all()

    def _record_clear(self, kind: str, snapshots: list[HideSnapshot]) -> None:
        if not snapshots:
            return
        self.clear_undo.push(ClearUndoEntry(kind=kind, snapshots=snapshots))
        peek = self.clear_undo.peek()
        self.last_clear_message = peek.message if peek else None

    def clear_finished(self) -> list[int]:
        """Hide only completed/failed/cancelled. Pending and in-flight stay."""
        jobs = [j for j in self.repo.list_jobs() if j.status in TERMINAL_STATUSES]
        snaps = [
            HideSnapshot(j.id, j.queue_hidden, bool(j.options().get("history_hidden")))
            for j in jobs
        ]
        ids = self.repo.clear_finished_from_queue()
        self._record_clear("queue", snaps[:])
        return ids

    def clear_selected(self, job_ids: list[int]) -> list[int]:
        ids = [int(i) for i in job_ids]
        flag_rows = self.repo.snapshot_hide_flags(ids)
        snaps = [HideSnapshot(jid, qh, hh) for jid, qh, hh in flag_rows]
        cleared = self.repo.clear_from_queue(ids)
        kept = {s.job_id for s in snaps if s.job_id in set(cleared)}
        self._record_clear("queue", [s for s in snaps if s.job_id in kept])
        return cleared

    def clear_history_ids(self, job_ids: list[int]) -> int:
        ids = [int(i) for i in job_ids]
        flag_rows = self.repo.snapshot_hide_flags(ids)
        snaps = [HideSnapshot(jid, qh, hh) for jid, qh, hh in flag_rows]
        n = self.repo.clear_history(ids)
        self._record_clear("history", snaps)
        return n

    def undo_clear(self) -> int:
        entry = self.clear_undo.pop()
        if entry is None:
            self.last_clear_message = None
            return 0
        n = self.repo.restore_hide_flags(
            [(s.job_id, s.queue_hidden, s.history_hidden) for s in entry.snapshots]
        )
        peek = self.clear_undo.peek()
        self.last_clear_message = peek.message if peek else None
        return n

    def handle_fail_pause_action(
        self,
        action_id: str,
        job_id: int,
        *,
        authenticate: AuthFn | None = None,
        import_browser: ImportBrowserFn | None = None,
        ask_retry_resume: AskRetry | None = None,
    ) -> dict[str, Any]:
        """Same functions the fail-pause modal / failed-card Retry buttons call."""
        if action_id == "stop":
            self.worker.disarm()
            return {"action": "stop"}
        if action_id == "skip_resume":
            self.worker.request_download_all()
            return {"action": "skip_resume"}
        if action_id == "retry":
            try:
                job = self.repo.get(int(job_id))
                if job.options().get("error_category") == "output_missing" or job.options().get(
                    "archive_hit"
                ):
                    self.repo.merge_options(
                        job.id, {"force_redownload": True, "ignore_download_archive": True}
                    )
            except Exception:  # noqa: BLE001
                pass
            self.retry_job(job_id)
            return {"action": "retry", "job_id": job_id}
        if action_id == "authenticate":
            try:
                url = self.repo.get(job_id).url
            except KeyError:
                url = None
            if authenticate is not None:
                authenticate(url)
            return {"action": "authenticate", "url": url}
        if action_id == "import_browser":
            try:
                url = self.repo.get(job_id).url
            except KeyError:
                url = None
            if not url:
                return {"action": "import_browser", "url": None, "retried": False}
            recovered = self.recover_bot_cookies(
                url,
                import_browser=import_browser,
                probe=getattr(self, "cookie_probe", None),
            )
            if not recovered.get("ok"):
                return {
                    "action": "import_browser",
                    "url": url,
                    "retried": False,
                    "validated": False,
                    "message": recovered.get("message"),
                    "result": recovered.get("result"),
                }
            if ask_retry_resume is not None and ask_retry_resume():
                self.retry_job(job_id)
                return {
                    "action": "import_browser",
                    "url": url,
                    "retried": True,
                    "validated": True,
                    "result": recovered.get("result"),
                }
            return {
                "action": "import_browser",
                "url": url,
                "retried": False,
                "validated": True,
                "result": recovered.get("result"),
                "message": recovered.get("message"),
            }
        if action_id == "retry_resume":
            self.retry_and_resume(job_id)
            return {"action": "retry_resume", "job_id": job_id}
        return {"action": action_id}

    def maybe_fail_pause(self, job: Any) -> bool:
        return maybe_fail_pause(self.worker, self.repo, job)
