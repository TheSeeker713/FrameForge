"""Private library: copy, password zip, disguise, original disposition."""

from __future__ import annotations

from pathlib import Path

from frameforge.db.repository import JobRepository
from frameforge.library.ingest import ingest_completed_jobs
from frameforge.library.private import (
    dispose_originals,
    has_private_password,
    send_to_private,
    set_private_password,
    unlock_session,
    verify_password,
)
from frameforge.library.store import LibraryStore
from frameforge.library.zipcrypto import extract_password_zip, write_password_zip
from frameforge.util.recycle import FOF_ALLOWUNDO, recycle_flags


def _repo(tmp_path: Path) -> JobRepository:
    return JobRepository(tmp_path / "p.db")


def test_copy_not_move_zip_password_and_disguise(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = tmp_path / "dl" / "clip.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"private-media-bytes-0123456789")
    job = repo.enqueue("https://www.youtube.com/watch?v=priv", title="secret", extractor="youtube")
    repo.update_status(job.id, "completed")
    repo.set_paths(job.id, download_path=str(src), output_path=str(src))
    item = ingest_completed_jobs(repo, store)[0].item
    original = Path(item.path)
    assert original.is_file()
    set_private_password(store, "hunter2")
    assert has_private_password(store)
    assert unlock_session(store, "hunter2")
    assert not unlock_session(store, "wrong")
    packs = send_to_private(store, [item.id], password="hunter2", disguise=True)
    assert len(packs) == 1
    assert original.is_file(), "copy must leave the original in place"
    assert packs[0].copied
    assert packs[0].container.suffix == ".ffpriv"
    assert packs[0].private_item.is_private
    extracted = extract_password_zip(packs[0].container, tmp_path / "out", password="hunter2")
    assert extracted.read_bytes() == b"private-media-bytes-0123456789"
    public = [i for i in store.list_items() if i.id == item.id]
    assert public
    privates = store.list_private_items()
    assert len(privates) == 1
    repo.close()


def test_wrong_password_fails_closed(tmp_path: Path):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"abc123xyz")
    z = write_password_zip(tmp_path / "a.zip", src, password="ok")
    try:
        extract_password_zip(z, tmp_path / "bad", password="nope")
        raise AssertionError("wrong password must fail")
    except PermissionError:
        pass
    hashed = "not-a-hash"
    assert verify_password("ok", hashed) is False
    assert verify_password("ok", None) is False
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    set_private_password(store, "ok")
    clip = tmp_path / "Lib" / "Uncategorized" / "x.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"x")
    item = store.add_item(path=clip, title="x")
    try:
        send_to_private(store, [item.id], password="nope")
        raise AssertionError("send_to_private must fail closed")
    except PermissionError:
        pass
    assert clip.is_file()
    repo.close()


def test_disposition_keep_trash_move(tmp_path: Path):
    repo = _repo(tmp_path)
    store = LibraryStore(repo)
    store.complete_onboarding(tmp_path / "Lib")
    src = tmp_path / "dl" / "keepme.mp4"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"orig")
    job = repo.enqueue("https://example.com/k", title="k")
    repo.update_status(job.id, "completed")
    repo.set_paths(job.id, download_path=str(src))
    item = ingest_completed_jobs(repo, store)[0].item
    original = Path(item.path)
    set_private_password(store, "pw")
    packs = send_to_private(store, [item.id], password="pw", disguise=False)
    assert packs[0].container.suffix == ".zip"
    dispose_originals(store, [original], mode="keep")
    assert original.is_file()
    dest = tmp_path / "external"
    dispose_originals(store, [original], mode="move", dest_dir=dest)
    assert not original.exists()
    assert (dest / original.name).is_file()
    assert store.get_by_path(original) is None

    src2 = tmp_path / "dl" / "trashme.mp4"
    src2.write_bytes(b"bye")
    job2 = repo.enqueue("https://example.com/t", title="t")
    repo.update_status(job2.id, "completed")
    repo.set_paths(job2.id, download_path=str(src2))
    item2 = ingest_completed_jobs(repo, store)[0].item
    orig2 = Path(item2.path)
    send_to_private(store, [item2.id], password="pw")
    dispose_originals(store, [orig2], mode="trash", recycle=False)
    assert not orig2.exists()
    repo.close()


def test_recycle_flags_allow_undo():
    assert recycle_flags() & FOF_ALLOWUNDO
