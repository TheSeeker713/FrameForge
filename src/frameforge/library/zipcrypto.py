"""Password zip using traditional ZipCrypto (not a security product)."""

from __future__ import annotations

import os
import struct
import time
import zlib
import zipfile
from pathlib import Path

_CRC_INIT = 0


def _crc32(data: bytes, crc: int = 0) -> int:
    return zlib.crc32(data, crc) & 0xFFFFFFFF


def _gen_crc(crc: int) -> int:
    for _j in range(8):
        if crc & 1:
            crc = (crc >> 1) ^ 0xEDB88320
        else:
            crc >>= 1
    return crc


_CRCTABLE = [_gen_crc(i) for i in range(256)]


class _ZipCrypto:
    """PKWARE ZipCrypto matching CPython zipfile._ZipDecrypter."""

    def __init__(self, password: bytes) -> None:
        self.key0 = 305419896
        self.key1 = 591751049
        self.key2 = 878082192
        for b in password:
            self._update(b)

    def _crc32(self, ch: int, crc: int) -> int:
        return (crc >> 8) ^ _CRCTABLE[(crc ^ ch) & 0xFF]

    def _update(self, b: int) -> None:
        self.key0 = self._crc32(b, self.key0)
        self.key1 = (self.key1 + (self.key0 & 0xFF)) & 0xFFFFFFFF
        self.key1 = (self.key1 * 134775813 + 1) & 0xFFFFFFFF
        self.key2 = self._crc32((self.key1 >> 24) & 0xFF, self.key2)

    def encrypt(self, data: bytes) -> bytes:
        out = bytearray(len(data))
        for i, b in enumerate(data):
            k = self.key2 | 2
            c = b ^ (((k * (k ^ 1)) >> 8) & 0xFF)
            self._update(b)
            out[i] = c
        return bytes(out)


def _dos_time(ts: float | None = None) -> tuple[int, int]:
    t = time.localtime(ts if ts is not None else time.time())
    dostime = (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)
    dosdate = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return dostime, dosdate


def write_password_zip(zip_path: str | Path, source: str | Path, *, password: str, arcname: str | None = None) -> Path:
    """Write a single-file ZipCrypto zip that Python zipfile can read with pwd=."""
    src = Path(source)
    data = src.read_bytes()
    name = arcname or src.name
    pwd = password.encode("utf-8")
    crc = _crc32(data)
    compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
    compressed = compressor.compress(data) + compressor.flush()
    crypto = _ZipCrypto(pwd)
    header = bytearray(os.urandom(12))
    header[11] = (crc >> 24) & 0xFF
    payload = crypto.encrypt(bytes(header) + compressed)
    dostime, dosdate = _dos_time(src.stat().st_mtime)
    name_b = name.encode("utf-8")
    flags = 0x0001 | 0x0800  # encrypted + UTF-8
    method = 8
    dest = Path(zip_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    local = struct.pack(
        "<4sHHHHHIIIHH",
        b"PK\x03\x04",
        20,
        flags,
        method,
        dostime,
        dosdate,
        crc,
        len(payload),
        len(data),
        len(name_b),
        0,
    )
    central = struct.pack(
        "<4sHHHHHHIIIHHHHHII",
        b"PK\x01\x02",
        20,
        20,
        flags,
        method,
        dostime,
        dosdate,
        crc,
        len(payload),
        len(data),
        len(name_b),
        0,
        0,
        0,
        0,
        0,
        0,  # relative offset of local header
    )
    eocd = struct.pack(
        "<4sHHHHIIH",
        b"PK\x05\x06",
        0,
        0,
        1,
        1,
        len(central) + len(name_b),
        len(local) + len(name_b) + len(payload),
        0,
    )
    dest.write_bytes(local + name_b + payload + central + name_b + eocd)
    return dest.resolve()


def extract_password_zip(zip_path: str | Path, dest_dir: str | Path, *, password: str) -> Path:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.setpassword(password.encode("utf-8"))
        try:
            bad = zf.testzip()
        except Exception as exc:  # noqa: BLE001 — wrong ZipCrypto pwd is zlib/RuntimeError
            raise PermissionError("Wrong password or damaged zip") from exc
        if bad:
            raise PermissionError("Wrong password or damaged zip")
        zf.extractall(dest)
        names = zf.namelist()
        if not names:
            raise FileNotFoundError("Empty private zip")
        out = dest / names[0]
        if not out.exists():
            raise FileNotFoundError(names[0])
        return out.resolve()
