"""Local Private library: copy + password zip + optional disguise. Not remote security."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from frameforge.library.models import LibraryItem
from frameforge.library.store import LibraryStore
from frameforge.library.zipcrypto import extract_password_zip, write_password_zip

SETTING_HASH = "library_private_hash"
SETTING_DISGUISE = "library_private_disguise_ext"
DEFAULT_DISGUISE = ".ffpriv"
PBKDF2_ROUNDS = 200_000


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("Password is required")
    raw = salt if salt is not None else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw, PBKDF2_ROUNDS)
    return raw.hex() + ":" + dk.hex()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or ":" not in stored:
        return False
    salt_hex, dk_hex = stored.split(":", 1)
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return hmac.compare_digest(got, expected)


def set_private_password(store: LibraryStore, password: str) -> None:
    store.set_setting(SETTING_HASH, hash_password(password))


def has_private_password(store: LibraryStore) -> bool:
    return bool(store.get_setting(SETTING_HASH))


def disguise_ext(store: LibraryStore) -> str:
    raw = store.get_setting(SETTING_DISGUISE, DEFAULT_DISGUISE) or DEFAULT_DISGUISE
    if not raw.startswith("."):
        raw = "." + raw
    return raw


@dataclass
class PrivatePackResult:
    private_item: LibraryItem
    container: Path
    original: Path
    copied: bool


def send_to_private(
    store: LibraryStore,
    item_ids: list[int],
    *,
    password: str,
    disguise: bool = False,
) -> list[PrivatePackResult]:
    """Copy each item into a password zip under Library/Private. Originals untouched."""
    stored = store.get_setting(SETTING_HASH)
    if not verify_password(password, stored):
        raise PermissionError("Private password is wrong or not set")
    priv = store.private_dir()
    results: list[PrivatePackResult] = []
    ext = disguise_ext(store) if disguise else ".zip"
    for item_id in item_ids:
        item = store.get(item_id)
        src = Path(item.path)
        if not src.is_file():
            raise FileNotFoundError(src)
        staging = priv / f".staging-{item.id}{src.suffix}"
        shutil.copy2(src, staging)
        zip_path = priv / f"{src.stem}-{item.id}.zip"
        write_password_zip(zip_path, staging, password=password, arcname=src.name)
        staging.unlink(missing_ok=True)
        container = zip_path
        if disguise:
            container = zip_path.with_suffix(ext)
            if container.exists():
                container.unlink()
            zip_path.rename(container)
        private_item = store.add_item(
            path=container,
            title=item.title,
            source=item.source,
            job_id=None,
            width=item.width,
            height=item.height,
            thumb_path=item.thumb_path,
            is_private=True,
        )
        results.append(
            PrivatePackResult(
                private_item=private_item,
                container=container.resolve(),
                original=src.resolve(),
                copied=True,
            )
        )
    return results


def unlock_session(store: LibraryStore, password: str) -> bool:
    return verify_password(password, store.get_setting(SETTING_HASH))


def play_private_item(
    store: LibraryStore,
    item: LibraryItem,
    *,
    password: str,
    launch: bool = True,
) -> Path:
    from frameforge.util.reveal import open_in_default_player

    stored = store.get_setting(SETTING_HASH)
    if not verify_password(password, stored):
        raise PermissionError("Wrong password")
    temp = store.private_dir() / "play"
    dest_dir = temp / str(item.id)
    if dest_dir.exists():
        shutil.rmtree(dest_dir, ignore_errors=True)
    extracted = extract_password_zip(item.path, dest_dir, password=password)
    return open_in_default_player(extracted, launch=launch)


def export_private_item(item: LibraryItem, dest_dir: str | Path) -> Path:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    src = Path(item.path)
    out = dest / src.name
    shutil.copy2(src, out)
    return out.resolve()


def remove_private_item(store: LibraryStore, item_id: int, *, delete_container: bool = True) -> None:
    item = store.get(item_id)
    path = Path(item.path)
    store.remove_item(item_id)
    if delete_container and path.is_file():
        path.unlink()


def dispose_originals(
    store: LibraryStore,
    originals: list[Path],
    *,
    mode: str,
    dest_dir: str | Path | None = None,
    recycle: bool = True,
) -> None:
    """Keep, Recycle Bin, or move originals after a Private pack. Copies already exist."""
    from frameforge.util.recycle import send_to_recycle_bin

    if mode == "keep":
        return
    for original in originals:
        path = Path(original)
        if not path.exists():
            continue
        public = store.get_by_path(path)
        if mode == "trash":
            send_to_recycle_bin(path, recycle=recycle)
            if public:
                store.remove_item(public.id)
        elif mode == "move":
            if dest_dir is None:
                raise ValueError("Move destination is required")
            folder = Path(dest_dir)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / path.name
            shutil.move(str(path), str(target))
            if public:
                store.remove_item(public.id)
        else:
            raise ValueError(f"Unknown disposition {mode!r}")

