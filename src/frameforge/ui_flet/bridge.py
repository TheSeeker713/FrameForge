"""Toolkit-free command bridge: Flet (and tests) call these handlers, never the worker loop."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
        return self.repo.enqueue(url, **kwargs)

    def retry_job(self, job_id: int) -> None:
        """Reset one failed job to pending and arm download for that id (explicit Retry)."""
        job = self.repo.get(int(job_id))
        self.repo.update_status(job.id, "pending", error=None, progress=0)
        self.repo.merge_options(job.id, {"fail_pause": False, "queue_hidden": False})
        self.worker.request_download_ids([job.id])

    def download_selected(self, job_ids: list[int]) -> None:
        pending = [i for i in job_ids if self.repo.get(i).status == "pending"]
        if pending:
            self.worker.request_download_ids(pending)

    def download_all_pending(self) -> None:
        self.worker.request_download_all()

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
            result = import_browser(url) if import_browser is not None else None
            ok = bool(getattr(result, "ok", False)) if result is not None else False
            if ok and ask_retry_resume is not None and ask_retry_resume():
                self.retry_job(job_id)
                return {"action": "import_browser", "url": url, "retried": True, "result": result}
            return {
                "action": "import_browser",
                "url": url,
                "retried": False,
                "result": result,
            }
        return {"action": action_id}

    def maybe_fail_pause(self, job: Any) -> bool:
        return maybe_fail_pause(self.worker, self.repo, job)
