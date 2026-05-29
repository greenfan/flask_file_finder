from __future__ import annotations

import os
import stat
import tarfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .db import ArchiveDB
from .detector import best_guess_mime, detect_archive

ProgressCallback = Callable[[str, dict], None]


@dataclass
class ScanResult:
    root: str
    files_seen: int = 0
    files_updated: int = 0
    archives_found: int = 0
    errors: int = 0
    nested_entries: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0


def _record_error(db: ArchiveDB, path: str, error: str, result: ScanResult, progress_cb: Optional[ProgressCallback]) -> None:
    db.insert_error(path, error)
    result.errors += 1
    if progress_cb:
        progress_cb("error", {"path": path, "error": error, "errors": result.errors})


def _maybe_nested_entries(path: str, include_nested: bool, result: ScanResult, progress_cb: Optional[ProgressCallback]) -> None:
    if not include_nested:
        return
    lower = path.lower()
    try:
        nested_suffixes = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
        if lower.endswith(".zip") and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if any(info.filename.lower().endswith(suf) for suf in nested_suffixes):
                        result.nested_entries += 1
                        if progress_cb:
                            progress_cb("nested", {"path": f"{path}::{info.filename}", "size": info.file_size})
        elif any(lower.endswith(suf) for suf in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")) and tarfile.is_tarfile(path):
            with tarfile.open(path) as tf:
                for member in tf.getmembers():
                    if any(member.name.lower().endswith(suf) for suf in nested_suffixes):
                        result.nested_entries += 1
                        if progress_cb:
                            progress_cb("nested", {"path": f"{path}::{member.name}", "size": member.size})
    except Exception as exc:
        if progress_cb:
            progress_cb("nested_error", {"path": path, "error": str(exc)})


def scan_directory(root: str | Path, db: ArchiveDB, *, include_nested: bool = False, follow_symlinks: bool = False, force: bool = False, progress_cb: Optional[ProgressCallback] = None) -> ScanResult:
    root_path = Path(root).expanduser().resolve(strict=False)
    if not root_path.exists():
        raise FileNotFoundError(f"Root path does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Root path is not a directory: {root_path}")

    result = ScanResult(root=str(root_path), started_at=time.time())
    if progress_cb:
        progress_cb("started", {"root": result.root, "started_at": result.started_at, "mode": "force" if force else "incremental"})

    def onerror(exc: OSError):
        _record_error(db, getattr(exc, "filename", str(root_path)), str(exc), result, progress_cb)

    for current_root, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=follow_symlinks, onerror=onerror):
        for name in filenames:
            path = os.path.join(current_root, name)
            result.files_seen += 1
            try:
                st = os.stat(path, follow_symlinks=False)
            except OSError as exc:
                _record_error(db, path, str(exc), result, progress_cb)
                continue

            if stat.S_ISLNK(st.st_mode) and not follow_symlinks:
                _record_error(db, path, "skipped symlink (followlinks disabled)", result, progress_cb)
                continue
            if not stat.S_ISREG(st.st_mode):
                continue

            existing = db.get_file(path)
            if existing and not force:
                unchanged = (
                    existing["size"] == st.st_size
                    and existing["mtime"] == st.st_mtime
                    and existing["inode"] == st.st_ino
                    and existing["device"] == st.st_dev
                )
                if unchanged:
                    db.touch_seen(path)
                    continue

            detected = detect_archive(path)
            is_archive = bool(detected["is_archive"])
            ftype = "archive" if is_archive else None
            mime = detected["mime"] or best_guess_mime(path)
            db.upsert_file(
                root=str(root_path),
                path=os.path.abspath(path),
                size=st.st_size,
                mtime=st.st_mtime,
                inode=st.st_ino,
                device=st.st_dev,
                ftype=ftype,
                mime=mime,
                detected_by=detected["detected_by"],
                last_seen=time.time(),
            )
            result.files_updated += 1
            if is_archive:
                result.archives_found += 1
                _maybe_nested_entries(path, include_nested, result, progress_cb)
            if progress_cb and result.files_updated % 100 == 0:
                progress_cb("updated", {"files_updated": result.files_updated, "archives_found": result.archives_found, "errors": result.errors})

    stale = db.delete_stale_root(str(root_path), result.started_at)
    if stale and progress_cb:
        progress_cb("stale_removed", {"count": stale})
    result.finished_at = time.time()
    if progress_cb:
        progress_cb("finished", {
            "root": result.root,
            "files_seen": result.files_seen,
            "files_updated": result.files_updated,
            "archives_found": result.archives_found,
            "errors": result.errors,
            "nested_entries": result.nested_entries,
            "finished_at": result.finished_at,
        })
    return result
