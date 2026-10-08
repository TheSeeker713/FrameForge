"""Eporner sends two hashes. The video API only accepts player.hash."""

from __future__ import annotations

from pathlib import Path

from frameforge.download.eporner import eporner_embed_url, plugin_root, select_eporner_hash
from frameforge.download.recovery import next_recovery_step
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.errors import AUTH_REQUIRED, classify_error

PAGE = """
<title>Clip - EPORNER</title>
<script>EP.user.hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";</script>
<script>player.hash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";</script>
"""
SCREENSHOT = (
    "ERROR: [Eporner] TtOBNI7X9eU: Eporner said: Authorization failed. Try to reload page.\n"
)
URL = "https://www.eporner.com/video-TtOBNI7X9eU/476/"


def test_player_hash_wins_over_the_user_hash():
    assert select_eporner_hash(PAGE) == "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_single_hash_page_still_matches():
    page = '<script>hash: "cccccccccccccccccccccccccccccccc"</script>'
    assert select_eporner_hash(page) == "cccccccccccccccccccccccccccccccc"


def test_screenshot_retries_embed_then_cookies():
    assert classify_error(SCREENSHOT, url=URL) == AUTH_REQUIRED
    assert eporner_embed_url(URL) == "https://www.eporner.com/embed/TtOBNI7X9eU/"
    assert eporner_embed_url("https://www.eporner.com/embed/TtOBNI7X9eU/") is None
    assert (
        next_recovery_step(
            ["impersonate"],
            category=None,
            message=SCREENSHOT,
            url=URL,
            impersonated=True,
            has_impersonate_targets=True,
            silent_cookies=True,
        )
        == "eporner_embed"
    )
    assert (
        next_recovery_step(
            ["impersonate", "eporner_embed"],
            category=AUTH_REQUIRED,
            message=SCREENSHOT,
            url="https://www.eporner.com/embed/TtOBNI7X9eU/",
            impersonated=True,
            has_impersonate_targets=True,
            silent_cookies=True,
        )
        == "silent_firefox_cookies"
    )


def test_cli_loads_the_player_hash_plugin(tmp_path: Path):
    dl = YtDlpDownloader(output_dir=tmp_path, archive_file=tmp_path / "a.txt", use_aria2c=False)
    cmd = dl._build_cli_cmd(URL)
    assert "--plugin-dirs" in cmd
    assert plugin_root() in cmd
    assert (Path(plugin_root()) / "frameforge" / "yt_dlp_plugins" / "extractor" / "eporner.py").is_file()


def test_plugin_extractor_is_the_one_yt_dlp_uses():
    from yt_dlp.globals import all_plugins_loaded
    from yt_dlp.utils import encode_base_n

    from frameforge.download.eporner import ensure_plugin_loaded

    all_plugins_loaded.value = False
    ensure_plugin_loaded()
    from yt_dlp import YoutubeDL

    ydl = YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True})
    ie = ydl.get_info_extractor("Eporner")
    assert type(ie).__module__.startswith("yt_dlp_plugins")

    seen: dict[str, str] = {}

    def calc_hash(value: str) -> str:
        return "".join(encode_base_n(int(value[lb : lb + 8], 16), 36) for lb in range(0, 32, 8))

    class _Handle:
        url = URL

    ie._download_webpage_handle = lambda *args, **kwargs: (PAGE, _Handle())

    def _download_json(*args, **kwargs):
        seen["hash"] = kwargs.get("query", {}).get("hash", "")
        return {"available": False, "message": "stopped in test"}

    ie._download_json = _download_json
    try:
        ie._real_extract(URL)
    except Exception as exc:
        assert "stopped in test" in str(exc)
    assert seen["hash"] == calc_hash("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    assert seen["hash"] != calc_hash("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
