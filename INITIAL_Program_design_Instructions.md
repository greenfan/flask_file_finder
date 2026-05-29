## Program: `archive_indexer`

### Goal
Scan a supplied Linux directory recursively, including hidden files, to find **all archive/compressed files**, cache results, and expose them through a **Flask web UI**.

---

## Core Design

### 1. Scanner
Python-based recursive filesystem scanner.

Use:

```python
os.scandir()
```

or preferably:

```python
os.walk(..., followlinks=False)
```

Rules:

- Scan every file and directory, including dotfiles.
- Do not skip hidden paths.
- Do not follow symlinks by default to avoid loops.
- Record permission errors, broken symlinks, unreadable dirs.
- Store absolute path, size, mtime, inode, device ID.

---

## 2. Archive Detection

Detect by both:

### Extension
Recognize:

```text
.zip
.tar
.tar.gz
.tgz
.tar.bz2
.tbz2
.tar.xz
.txz
.gz
.bz2
.xz
.zst
.7z
.rar
.iso
.cab
.lz
.lzma
.br
```

### Magic bytes
Use `python-magic` / `libmagic`.

Fallback to Python stdlib where possible:

```python
zipfile.is_zipfile()
tarfile.is_tarfile()
gzip
bz2
lzma
```

Store detection reason:

```text
extension
magic
both
```

---

## 3. Cache

Use SQLite.

Database file:

```text
~/.cache/archive_indexer/index.sqlite
```

Schema:

```sql
files(
  id INTEGER PRIMARY KEY,
  root TEXT,
  path TEXT UNIQUE,
  size INTEGER,
  mtime REAL,
  inode INTEGER,
  device INTEGER,
  type TEXT,
  mime TEXT,
  detected_by TEXT,
  last_seen REAL
)

scan_errors(
  id INTEGER PRIMARY KEY,
  path TEXT,
  error TEXT,
  timestamp REAL
)
```

Cache logic:

- If `path + size + mtime + inode` unchanged, do not rescan.
- Remove stale entries not seen in latest scan.
- Support manual “rescan” button.
- Support incremental scan.

---

## 4. CLI

Command:

```bash
archive-indexer scan /mount/mountHDD1
archive-indexer serve
archive-indexer rescan /mount/mountHDD1
archive-indexer stats
```

Options:

```bash
--follow-symlinks
--include-nested
--db /path/index.sqlite
--workers 8
--json
```

---

## 5. Flask Web UI

Routes:

```text
GET  /                 dashboard
GET  /archives         list archive/compressed files
GET  /archives?q=...   search paths
GET  /errors           scan errors
POST /scan             start scan
POST /rescan           force rescan
GET  /api/archives     JSON results
GET  /api/stats        JSON stats
```

UI features:

- Directory input box.
- Start scan button.
- Archive list table.
- Search/filter.
- Sort by size, type, path, modified time.
- Show scan status.
- Show errors.

---

## 6. Background Scanning

Use a background worker thread/process.

Avoid blocking Flask.

Simple approach:

```python
threading.Thread(target=scan_directory)
```

Better approach:

```text
RQ / Celery / APScheduler
```

For minimal implementation, use one background scan lock:

```python
scan_in_progress = True/False
```

---

## 7. Nested Archives

Optional advanced mode:

```bash
--include-nested
```

If enabled:

- Inspect archive contents without extracting permanently.
- Record virtual paths:

```text
/archive/foo.zip::inside/bar.tar.gz
```

Use safe temp extraction only if necessary.

Never extract blindly into user directories.

---

## 8. Safety

Important rules:

- Never execute files.
- Never extract archives by default.
- Avoid following symlink loops.
- Handle permission errors gracefully.
- Cap nested recursion depth.
- Log every skipped/error path.

---

## Recommended Python Stack

```text
Flask
SQLite
python-magic
tqdm optional
libarchive-c optional
```

Stdlib:

```text
os
stat
sqlite3
zipfile
tarfile
gzip
bz2
lzma
threading
pathlib
```

---

## Deliverable Structure

```text
archive_indexer/
  app.py          # Flask UI
  scanner.py      # filesystem scanner
  detector.py     # archive/compression detection
  db.py           # SQLite cache
  cli.py          # command-line interface
  templates/
    index.html
    archives.html
    errors.html
  static/
```

---

## Summary

Build a Python utility that recursively scans a directory, detects compressed/archive files by extension and magic bytes, caches results in SQLite, supports efficient incremental rescans, and exposes results through a minimal Flask web UI.
