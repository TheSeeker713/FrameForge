"""Serve the library studio and write every answer to docs/LIBRARY_DESIGN_FEEDBACK.md."""

from __future__ import annotations

import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
DOC = REPO / "docs" / "LIBRARY_DESIGN_FEEDBACK.md"
DATA = REPO / "docs" / "LIBRARY_DESIGN_FEEDBACK.json"
HOST = "127.0.0.1"
PORT = 8765


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def render_md(data: dict) -> str:
    status = "complete — use this file as the base for the Library plan" if data.get("status") == "complete" else "in progress"
    choices = data.get("choices") or {}
    lines = [
        "# Library module — design answers",
        "",
        "This file is overwritten by the library studio while it is open.",
        "Read it before planning the Library build. The videos stay where they already are; this session only chooses how the Library looks and behaves.",
        "",
        f"Status: {status}",
        f"Updated: {data.get('updated') or '—'}",
        f"Renderer: {data.get('backend') or '—'}",
        f"Frames per second (latest sample): {data.get('fps') if data.get('fps') is not None else '—'}",
        "",
        "## Chosen layers",
        "",
    ]
    if choices:
        for key, value in choices.items():
            if isinstance(value, dict):
                lines.append(f"- {value.get('group') or key}: {value.get('label') or value.get('id')}")
            else:
                lines.append(f"- {key}: {value}")
    else:
        lines.append("- None yet.")
    lines += ["", "## Manual shelf order", ""]
    order = data.get("order") or []
    if order:
        for index, title in enumerate(order, start=1):
            lines.append(f"{index}. {title}")
    else:
        lines.append("Not used yet.")
    lines += ["", "## Looks kept", ""]
    kept = data.get("kept") or []
    if kept:
        for shot in kept:
            bits = []
            for value in (shot.get("choices") or {}).values():
                if isinstance(value, dict):
                    bits.append(f"{value.get('group')}: {value.get('label')}")
            lines.append(f"- {shot.get('t')}: {'; '.join(bits)}")
    else:
        lines.append("None yet.")
    lines += ["", "## Looks discarded", ""]
    discarded = data.get("discarded") or []
    if discarded:
        for shot in discarded:
            bits = []
            for value in (shot.get("choices") or {}).values():
                if isinstance(value, dict):
                    bits.append(f"{value.get('group')}: {value.get('label')}")
            lines.append(f"- {shot.get('t')}: {'; '.join(bits)}")
    else:
        lines.append("None yet.")
    lines += ["", "## Notes", ""]
    notes = (data.get("notes") or "").strip()
    if notes:
        for row in notes.splitlines():
            lines.append(f"> {row}")
    else:
        lines.append("None yet.")
    lines += ["", "## Recent changes", ""]
    events = data.get("events") or []
    if events:
        for event in events[-40:]:
            lines.append(f"- {event.get('t')}: {event.get('label')}")
    else:
        lines.append("None yet.")
    lines += [
        "",
        "## Research this session is built from",
        "",
        "- Three.js 0.186 WebGPURenderer and TSL post-processing (anamorphic bloom, SSR). The studio uses the WebGL2 renderer so the Radeon 680M can run it, and draws the anamorphic streak as its own pass.",
        "- MeshPhysicalMaterial transmission, thickness, IOR, dispersion, and iridescence. Drei's MeshTransmissionMaterial (Codrops, March 2025) re-renders the scene per glass object; the built-in physical material shares one transmission pass.",
        "- A planar floor reflector, not screen-space reflections. SSR is the heavier WebGPU demo.",
        "- Infuse list-versus-poster threads (September 2025): long file names need a shelf, and a poster grid is a second view.",
        "- Jellyfin: removing a library does not delete the folder. There is still no first-class 'remove this title and keep the file' action, which is the gap FrameForge should close.",
        "",
    ]
    return "\n".join(lines)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] == "/api/feedback":
            if not DATA.exists():
                self.send_response(204)
                self.end_headers()
                return
            body = DATA.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/feedback":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 1_000_000:
            self.send_error(413)
            return
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self.send_error(400)
            return
        if not isinstance(data, dict):
            self.send_error(400)
            return
        _atomic(DATA, json.dumps(data, indent=2))
        _atomic(DOC, render_md(data))
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        if args and str(args[0]).startswith("POST"):
            super().log_message(fmt, *args)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Library studio at http://{HOST}:{PORT}/", flush=True)
    print(f"Answers write to {DOC}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
