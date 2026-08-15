"""YouTube Innertube player_client rotation for logged-out public downloads."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from frameforge.download.js_runtime import url_needs_js_runtime

DEFAULT_PLAYER_CLIENTS = "android_vr,tv_downgraded,web_embedded,web_safari"
INNERTUBE_SETTING = "youtube_innertube"
CLIENTS_SETTING = "youtube_player_clients"
YTDLP_DEFAULTS_SETTING = "youtube_use_ytdlp_clients"


def is_youtube_url(url: str) -> bool:
    return url_needs_js_runtime(url) or "youtube.com" in (urlparse(url).hostname or "").lower()


def player_client_list(raw: str | None = None) -> list[str]:
    text = (raw or DEFAULT_PLAYER_CLIENTS).strip() or DEFAULT_PLAYER_CLIENTS
    return [part.strip() for part in text.split(",") if part.strip()]


def innertube_enabled(repo: Any | None) -> bool:
    if repo is None or not hasattr(repo, "get_setting"):
        return True
    if str(repo.get_setting(YTDLP_DEFAULTS_SETTING, "0") or "0").strip() in {"1", "true", "yes"}:
        return False
    return str(repo.get_setting(INNERTUBE_SETTING, "1") or "1").strip() not in {"0", "false", "no"}


def extractor_args_cli(url: str, *, repo: Any | None = None, clients: str | None = None) -> str | None:
    """`--extractor-args` value, or None when URL is not YouTube / user chose yt-dlp defaults."""
    if not is_youtube_url(url) or not innertube_enabled(repo):
        return None
    if clients is None and repo is not None and hasattr(repo, "get_setting"):
        clients = str(repo.get_setting(CLIENTS_SETTING, DEFAULT_PLAYER_CLIENTS) or DEFAULT_PLAYER_CLIENTS)
    names = player_client_list(clients)
    if not names:
        return None
    return "youtube:player_client=" + ",".join(names)


def extractor_args_opts(url: str, *, repo: Any | None = None, clients: str | None = None) -> dict[str, Any] | None:
    cli = extractor_args_cli(url, repo=repo, clients=clients)
    if not cli:
        return None
    names = player_client_list(cli.split("=", 1)[-1])
    return {"youtube": {"player_client": names}}
