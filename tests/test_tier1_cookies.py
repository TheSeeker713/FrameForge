"""Tier 1.4 — cookie path helpers, yt-dlp cookiefile wiring, smart skip."""

from __future__ import annotations

from pathlib import Path

from frameforge.download import cookies as cookie_mod
from frameforge.download.ytdlp import YtDlpDownloader
from frameforge.paths import cookies_dir, ensure_output_tree


def test_cookies_dir_created():
    ensure_output_tree()
    assert cookies_dir().is_dir()


def test_domain_normalization_and_paths(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Re-import paths resolution uses USERPROFILE — ensure tree
    ensure_output_tree()
    assert cookie_mod.normalize_domain("https://www.YouTube.com/watch?v=1") == "youtube.com"
    assert cookie_mod.normalize_domain("youtu.be") == "youtu.be"
    path = cookie_mod.cookie_path_for_domain("youtube.com")
    assert path.name == "youtube.com.txt"
    assert path.parent.name == "cookies"


def test_smart_skip_and_import(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    domain = "example.com"
    assert cookie_mod.has_cookies(domain) is False
    assert cookie_mod.should_skip_auth_prompt(domain) is False

    src = tmp_path / "exported.txt"
    src.write_text(
        "# Netscape HTTP Cookie File\n"
        ".example.com\tTRUE\t/\tFALSE\t0\tname\tvalue\n",
        encoding="utf-8",
    )
    dest = cookie_mod.import_netscape_cookies(domain, src)
    assert dest.is_file()
    assert cookie_mod.has_cookies(domain) is True
    assert cookie_mod.should_skip_auth_prompt(domain) is True
    # Session mark alone also skips when no file? after clear with file still True
    cookie_mod.clear_session_prompts()
    assert cookie_mod.should_skip_auth_prompt(domain) is True  # file exists


def test_ytdlp_opts_include_cookiefile(tmp_path: Path):
    cookie = tmp_path / "site.txt"
    cookie.write_text("# Netscape\n.site.test\tTRUE\t/\tFALSE\t0\ta\tb\n", encoding="utf-8")
    dl = YtDlpDownloader(output_dir=tmp_path / "o", archive_file=tmp_path / "a.txt", use_aria2c=False)
    dl.cookiefile = cookie
    opts = dl.build_opts(None)
    assert opts.get("cookiefile") == str(cookie)

    dl2 = YtDlpDownloader(output_dir=tmp_path / "o2", archive_file=tmp_path / "a2.txt", use_aria2c=False)
    opts2 = dl2.build_opts(None)
    assert "cookiefile" not in opts2


def test_missing_cookiefile_does_not_crash(tmp_path: Path):
    dl = YtDlpDownloader(
        output_dir=tmp_path / "o",
        archive_file=tmp_path / "a.txt",
        use_aria2c=False,
        cookiefile=tmp_path / "missing.txt",
    )
    opts = dl.build_opts(None)
    assert "cookiefile" not in opts


def test_resolve_cookiefile_for_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    assert cookie_mod.resolve_cookiefile_for_url("https://example.org/x") is None
    src = tmp_path / "dummy.txt"
    src.write_text("# Netscape\n.example.org\tTRUE\t/\tFALSE\t0\tk\tv\n", encoding="utf-8")
    cookie_mod.import_netscape_cookies("example.org", src)
    resolved = cookie_mod.resolve_cookiefile_for_url("https://example.org/watch")
    assert resolved is not None
    assert resolved.is_file()


def test_reject_empty_and_garbage_import(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    header_only = tmp_path / "header.txt"
    header_only.write_text(cookie_mod.NETSCAPE_HEADER, encoding="utf-8")
    garbage = tmp_path / "garbage.txt"
    garbage.write_text("{not: 'cookies'}\n<html>nope</html>\n", encoding="utf-8")
    for bad in (empty, header_only, garbage):
        try:
            cookie_mod.import_netscape_cookies("example.net", bad)
            raise AssertionError(f"expected reject for {bad.name}")
        except ValueError as exc:
            assert "Netscape" in str(exc)
    assert cookie_mod.has_cookies("example.net") is False
    assert cookie_mod.is_netscape_cookie_text("") is False
    assert cookie_mod.is_netscape_cookie_text(cookie_mod.NETSCAPE_HEADER) is False


def test_httponly_netscape_and_safe_filename(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    src = tmp_path / "ho.txt"
    src.write_text(
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\tSID\tsecret\n",
        encoding="utf-8",
    )
    dest = cookie_mod.import_netscape_cookies("https://www.YouTube.com/watch?v=1", src)
    assert dest.name == "youtube.com.txt"
    assert dest.parent.name == "cookies"
    assert cookie_mod.has_cookies("youtube.com")
    assert cookie_mod.cookie_filename("YouTube.com") == "youtube.com.txt"
    # Path-like junk in URL must not escape cookies dir
    name = cookie_mod.cookie_filename("https://evil.example/../../passwd")
    assert ".." not in name
    assert name.endswith(".txt")
    path = cookie_mod.cookie_path_for_domain("evil.example")
    assert path.parent.name == "cookies"
    assert path.name == "evil.example.txt"


def test_header_only_stub_is_not_reusable_cookies(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    stub = cookie_mod.ensure_cookie_stub("stub.example")
    assert stub.is_file()
    assert cookie_mod.has_cookies("stub.example") is False
    assert cookie_mod.resolve_cookiefile_for_url("https://stub.example/v") is None
    # Session skip still works after an explicit prompt mark
    cookie_mod.mark_session_prompted("stub.example")
    assert cookie_mod.should_skip_auth_prompt("stub.example") is True
    cookie_mod.clear_session_prompts()
    assert cookie_mod.should_skip_auth_prompt("stub.example") is False


def test_cookie_store_status_lists_domain_files(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    cookie_mod.clear_session_prompts()
    ensure_output_tree()
    src = tmp_path / "yt.txt"
    src.write_text(
        "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tFALSE\t0\tSID\tx\n",
        encoding="utf-8",
    )
    cookie_mod.import_netscape_cookies("youtube.com", src)
    status = cookie_mod.cookie_store_status()
    assert Path(str(status["directory"])).name == "cookies"
    assert "youtube.com.txt" in str(status["label"])
    names = [item["name"] for item in status["files"]]  # type: ignore[index]
    assert "youtube.com.txt" in names


def test_open_cookies_folder_is_cookies_dir_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    ensure_output_tree()
    from frameforge.paths import cookies_dir
    from frameforge.util.reveal import explorer_open_folder_command

    folder = cookies_dir().resolve()
    cmd = explorer_open_folder_command(folder)
    assert cmd[0] == "explorer"
    assert cmd[1] == str(folder)
    opened = cookie_mod.open_cookies_folder(launch=False)
    assert opened.resolve() == folder
    assert opened.name.lower() == "cookies"
