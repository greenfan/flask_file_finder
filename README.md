# archive_indexer

> A lean Linux archive indexer. Recursive. Cached. LAN-ready. No ceremony.

I built this because too many open-source disk/file indexers are either half-finished, heavyweight, or quietly useless once you point them at a real filesystem.

`archive_indexer` does one job: scan a directory, find archive/compressed files, cache the results in SQLite, and serve them through a small Flask UI on port `19000`.

## What it does

- Recursively scans Linux directories, including hidden paths
- Detects archives by extension and magic bytes
- Caches results in SQLite at `~/.cache/archive_indexer/index.sqlite`
- Serves a Flask UI on the LAN by default (`0.0.0.0:19000`)
- Records scan errors instead of pretending they do not exist
- Supports incremental rescans
- Keeps nested-archive detection optional

## Run it

```bash
archive-indexer serve
```

Then open:

```text
http://<host-ip>:19000/
```

## CLI

```bash
archive-indexer scan /path/to/root
archive-indexer rescan /path/to/root
archive-indexer stats
archive-indexer serve --host 0.0.0.0 --port 19000
```

## Web UI

- `/` — dashboard
- `/archives` — archive list
- `/errors` — scan errors
- `/api/archives` — JSON archive data
- `/api/stats` — JSON stats
- `/healthz` — health check

## Philosophy

- No archive extraction by default
- No symlink games unless explicitly requested
- No fake progress bars
- No pretending permission errors are “fine”

## Notes

- Linux-first
- SQLite-backed
- Flask-served
- Built for people who want to find files, not admire frameworks
