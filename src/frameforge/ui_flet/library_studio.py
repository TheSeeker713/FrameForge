"""Library shelf payload and the local page that hosts design/library-studio.

The studio stays a module of this app. This server only answers 127.0.0.1.
It does not write design feedback, move video files, or open a browser.
"""

from __future__ import annotations

import json
import mimetypes
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Locked look from docs/LIBRARY_DESIGN_FEEDBACK.md. The design studio can still
# change layers; the embedded shelf cannot.
LOCKED_LOOK: dict[str, Any] = {
    "shelf": "coverflow",
    "material": "glass",
    "pointer": "magnetic",
    "player": "expand",
    "anamorphic": True,
    "reflection": True,
    "grain": False,
    "vignette": True,
}

# Flet paints this under the WebGL surface so the shelf rectangle can be found.
# It matches the studio clear color.
SHELF_MARKER = "#0C0B0A"
MARKER_RGB = (12, 11, 10)

_STUDIO = Path(__file__).resolve().parents[3] / "design" / "library-studio"
mimetypes.add_type("text/javascript", ".js")


def studio_dir() -> Path:
    return _STUDIO


def _meta(item: Any) -> str:
    parts: list[str] = []
    source = getattr(item, "source", None)
    if source:
        parts.append(str(source))
    label = getattr(item, "resolution_label", "") or ""
    if label and label != "—":
        parts.append(str(label))
    duration = getattr(item, "duration", None)
    if duration:
        total = int(float(duration))
        parts.append(f"{total // 60}:{total % 60:02d}")
    added = str(getattr(item, "date_added", "") or "").split("T", 1)[0]
    if added:
        parts.append(added)
    return " · ".join(parts)


def shelf_document(items: list[Any], albums: list[Any] | None = None) -> tuple[dict[str, Any], dict[int, Path]]:
    """Rows for the studio. Paths are the files already on disk. Thumbs are ids, not copies."""
    thumbs: dict[int, Path] = {}
    clips: list[dict[str, Any]] = []
    for item in items:
        item_id = int(item.id)
        title = item.title or Path(str(item.path)).name
        thumb_url = None
        raw = getattr(item, "thumb_path", None)
        if raw and Path(raw).is_file():
            thumbs[item_id] = Path(raw)
            thumb_url = f"/media/thumb/{item_id}"
        clips.append(
            {
                "id": str(item_id),
                "item_id": item_id,
                "title": title,
                "meta": _meta(item),
                "hue": (item_id * 47) % 360,
                "thumb": thumb_url,
                "path": str(item.path),
                "album_id": getattr(item, "primary_collection_id", None),
            }
        )
    album_rows = [
        {"id": int(col.id), "name": col.name}
        for col in (albums or [])
    ]
    document = {"look": dict(LOCKED_LOOK), "clips": clips, "albums": album_rows}
    return document, thumbs


class LibraryShelfServer:
    """Serves the studio and the current library rows on an ephemeral localhost port."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._document: dict[str, Any] = {"look": dict(LOCKED_LOOK), "clips": [], "albums": []}
        self._thumbs: dict[int, Path] = {}
        self.rev = 0
        self.actions: list[dict[str, Any]] = []
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port = 0

    def start(self) -> None:
        if self._httpd is not None:
            return
        handler = self._handler_class()
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        httpd.daemon_threads = True
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        thread = threading.Thread(target=httpd.serve_forever, name="library-studio", daemon=True)
        thread.start()
        self._thread = thread

    def update(self, document: dict[str, Any], thumbs: dict[int, Path]) -> None:
        with self._lock:
            self._document = document
            self._thumbs = dict(thumbs)
            self.rev += 1

    def snapshot(self) -> tuple[dict[str, Any], dict[int, Path]]:
        with self._lock:
            return self._document, dict(self._thumbs)

    def page_url(self) -> str:
        self.start()
        return f"http://127.0.0.1:{self.port}/?embed=1&rev={self.rev}"

    def take_actions(self) -> list[dict[str, Any]]:
        with self._lock:
            found = list(self.actions)
            self.actions.clear()
            return found

    def close(self) -> None:
        httpd = self._httpd
        self._httpd = None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        thread = self._thread
        if thread is not None and thread.is_alive() and threading.current_thread() is not thread:
            thread.join(timeout=2)
        self._thread = None

    def _remember(self, action: dict[str, Any]) -> None:
        with self._lock:
            self.actions.append(action)

    def _handler_class(self) -> type[SimpleHTTPRequestHandler]:
        owner = self

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(_STUDIO), **kwargs)
            def log_message(self, fmt: str, *args: Any) -> None:
                return

            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path == "/api/shelf":
                    document, _thumbs = owner.snapshot()
                    self._send(200, json.dumps(document).encode("utf-8"), "application/json")
                    return
                if path.startswith("/media/thumb/"):
                    raw = path.rsplit("/", 1)[-1]
                    if not raw.isdigit():
                        self.send_error(404)
                        return
                    _document, thumbs = owner.snapshot()
                    file_path = thumbs.get(int(raw))
                    if file_path is None or not file_path.is_file():
                        self.send_error(404)
                        return
                    data = file_path.read_bytes()
                    kind = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                    self._send(200, data, kind)
                    return
                if path in {"", "/"}:
                    self.path = "/index.html"
                super().do_GET()

            def do_POST(self) -> None:  # noqa: N802
                path = urlparse(self.path).path
                if path != "/api/shelf/action":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length <= 0 or length > 100_000:
                    self.send_error(400)
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError):
                    self.send_error(400)
                    return
                action = str(payload.get("action") or "")
                raw_id = payload.get("id")
                if action not in {"open", "unlink", "delete"} or raw_id is None:
                    self.send_error(400)
                    return
                try:
                    item_id = int(raw_id)
                except (TypeError, ValueError):
                    self.send_error(400)
                    return
                owner._remember({"action": action, "id": item_id})
                self._send(200, b'{"ok":true}', "application/json")

            def translate_path(self, path: str) -> str:
                clean = urlparse(path).path
                rel = clean.lstrip("/") or "index.html"
                target = (_STUDIO / rel).resolve()
                if _STUDIO.resolve() not in target.parents and target != _STUDIO.resolve():
                    return str(_STUDIO / "index.html")
                return str(target)

        return Handler
