"""Books and folders are database links. An empty library still has the shelves."""

from __future__ import annotations

from pathlib import Path

from frameforge.library.books import classify, ensure_books, file_item
from frameforge.library.ingest import link_files
from frameforge.library.store import LibraryStore
from frameforge.queue.worker import SequentialWorker
from frameforge.ui_flet.app import FrameForgeUi
from tests.test_library import _clip, _repo


def test_empty_library_still_has_books_and_folders(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    ensure_books(store)
    movies = store.get_collection_by_name("Movies", "book")
    comedy = store.get_collection_by_name("Comedy", "book:Movies")
    porn = store.get_collection_by_name("Porn", "book")
    assert movies is not None and comedy is not None and porn is not None
    assert store.list_items() == []
    assert not (tmp_path / "Movies").exists()
    repo.close()


def test_classify_movies_tv_social_and_porn():
    assert classify(r"D:\films\Heat (1995) action.mp4") == ("Movies", "Action")
    assert classify(r"D:\films\300 (2006).mp4") == ("Movies", "Other")
    assert classify(r"D:\shows\Show.S01E02.mkv", title="Show") == ("TV Shows", "Other")
    assert classify(r"K:\downloads\social\youtube\standup comedy night.mp4") == ("YouTube", "Comedy")
    assert classify(r"K:\downloads\social\facebook\how-to lecture.mp4") == ("Facebook", "Informational")
    assert classify(r"K:\downloads\social\x.com\ai fiction short.mp4") == ("X", "AI Fiction")
    assert classify(r"K:\downloads\porn\eporner.com\clip.mp4") == ("Porn", "Unsorted")
    assert classify(r"K:\downloads\social\youtube\esoteric symbols.mp4") == ("YouTube", "Esoteric")


def test_link_files_sorts_without_moving(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    src = _clip(tmp_path / "inbox" / "Office Space (1999) comedy.mp4")
    added = link_files(store, [src])
    assert src.is_file()
    assert Path(added[0].path).resolve() == src.resolve()
    col = store.get_collection(added[0].primary_collection_id)
    assert col.kind == "book:Movies"
    assert col.name == "Comedy"
    repo.close()


def test_file_item_does_not_treat_a_leading_number_as_a_season(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    src = _clip(tmp_path / "300.mp4")
    item = store.add_item(path=src, title="300", source="Other")
    book, folder = file_item(store, item.id, path=str(src), title="300", source="Other", duration=None)
    assert book == "Other Videos"
    assert folder == "Other"
    assert src.is_file()
    repo.close()


def test_library_tab_shows_books_when_nothing_has_been_downloaded(tmp_path: Path):
    repo = _repo(tmp_path)
    worker = SequentialWorker(repo, download_handler=lambda j, r: None, poll_interval=0.05)
    ui = FrameForgeUi(repo=repo, worker=worker, start_worker=False, recover_on_launch=False)
    ui.reveal_launch = False
    ui.build()
    ui.refresh_library()
    data = ui.library_browser.data
    assert data["kind"] == "library_books"
    assert "Movies" in data["books"]
    assert "Porn" in data["books"]
    assert "YouTube" in data["books"]
    assert "Comedy" in data["folders"]
    assert data["clips"] == []
    assert ui.library_studio_host.visible is False
    assert ui.library_browser in ui.library_stack.controls
    ui.shutdown()
