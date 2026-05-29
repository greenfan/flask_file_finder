from __future__ import annotations

import mimetypes
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

try:
    import magic  # type: ignore
except Exception:  # pragma: no cover
    magic = None

ARCHIVE_SUFFIXES = (
    ".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst",
    ".tgz", ".tbz2", ".txz",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".zst",
    ".7z", ".rar", ".iso", ".cab", ".lz", ".lzma", ".br",
)

MIME_SUFFIX_HINTS = {
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".tgz": "application/gzip",
    ".gz": "application/gzip",
    ".bz2": "application/x-bzip2",
    ".xz": "application/x-xz",
    ".zst": "application/zstd",
    ".7z": "application/x-7z-compressed",
    ".rar": "application/vnd.rar",
    ".iso": "application/x-iso9660-image",
    ".cab": "application/vnd.ms-cab-compressed",
    ".lz": "application/x-lzip",
    ".lzma": "application/x-lzma",
    ".br": "application/x-brotli",
    ".tbz2": "application/x-bzip2",
    ".txz": "application/x-xz",
    ".tar.gz": "application/gzip",
    ".tar.bz2": "application/x-bzip2",
    ".tar.xz": "application/x-xz",
    ".tar.zst": "application/zstd",
}

MAGIC_PREFIXES = {
    b"PK\x03\x04": "application/zip",
    b"PK\x05\x06": "application/zip",
    b"PK\x07\x08": "application/zip",
    b"\x1f\x8b": "application/gzip",
    b"BZh": "application/x-bzip2",
    b"\xfd7zXZ\x00": "application/x-xz",
    b"\x28\xb5\x2f\xfd": "application/zstd",
    b"7z\xbc\xaf\x27\x1c": "application/x-7z-compressed",
    b"Rar!\x1a\x07\x00": "application/vnd.rar",
    b"Rar!\x1a\x07\x01\x00": "application/vnd.rar",
}


def _suffix_match(name: str) -> tuple[bool, Optional[str]]:
    lower = name.lower()
    for suffix in ARCHIVE_SUFFIXES:
        if lower.endswith(suffix):
            return True, MIME_SUFFIX_HINTS.get(suffix)
    return False, None


def _magic_match(path: str) -> tuple[bool, Optional[str]]:
    if magic is not None:
        try:
            mime = magic.from_file(path, mime=True)
            if mime and any(key in mime for key in ("zip", "gzip", "bzip2", "xz", "zstd", "rar", "7z", "tar", "cab", "iso", "lzip", "brotli")):
                return True, mime
        except Exception:
            pass

    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except Exception:
        return False, None

    for prefix, mime in MAGIC_PREFIXES.items():
        if head.startswith(prefix):
            return True, mime

    try:
        if zipfile.is_zipfile(path):
            return True, "application/zip"
    except Exception:
        pass
    try:
        if tarfile.is_tarfile(path):
            return True, "application/x-tar"
    except Exception:
        pass
    return False, None


def detect_archive(path: str) -> dict:
    name = Path(path).name
    ext_match, ext_mime = _suffix_match(name)
    magic_match, magic_mime = _magic_match(path)
    if ext_match and magic_match:
        detected_by = "both"
    elif ext_match:
        detected_by = "extension"
    elif magic_match:
        detected_by = "magic"
    else:
        detected_by = None
    return {
        "is_archive": ext_match or magic_match,
        "detected_by": detected_by,
        "mime": magic_mime or ext_mime or mimetypes.guess_type(path)[0],
    }


def best_guess_mime(path: str, fallback: Optional[str] = None) -> Optional[str]:
    guess, _ = mimetypes.guess_type(path)
    return guess or fallback
