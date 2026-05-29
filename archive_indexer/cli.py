from __future__ import annotations

import argparse
import json
from pathlib import Path

from .app import main as serve_main
from .db import ArchiveDB
from .scanner import scan_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive-indexer")
    parser.add_argument("--db", default=None, help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a directory")
    scan.add_argument("root")
    scan.add_argument("--follow-symlinks", action="store_true")
    scan.add_argument("--include-nested", action="store_true")
    scan.add_argument("--force", action="store_true")
    scan.add_argument("--json", action="store_true")

    rescan = sub.add_parser("rescan", help="Force rescan a directory")
    rescan.add_argument("root")
    rescan.add_argument("--follow-symlinks", action="store_true")
    rescan.add_argument("--include-nested", action="store_true")
    rescan.add_argument("--json", action="store_true")

    stats = sub.add_parser("stats", help="Show cached statistics")
    stats.add_argument("--json", action="store_true")

    serve = sub.add_parser("serve", help="Run Flask web UI")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=19000)
    serve.add_argument("--debug", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db = ArchiveDB(args.db)

    if args.command == "serve":
        serve_main(host=args.host, port=args.port, db_path=args.db, debug=args.debug)
        return 0

    if args.command == "stats":
        payload = db.stats()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    root = args.root
    result = scan_directory(
        root,
        db,
        include_nested=getattr(args, "include_nested", False),
        follow_symlinks=getattr(args, "follow_symlinks", False),
        force=getattr(args, "force", False) or args.command == "rescan",
    )
    payload = {
        "root": result.root,
        "files_seen": result.files_seen,
        "files_updated": result.files_updated,
        "archives_found": result.archives_found,
        "errors": result.errors,
        "nested_entries": result.nested_entries,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"Scanned {payload['files_seen']} files, updated {payload['files_updated']} records, found {payload['archives_found']} archives, errors {payload['errors']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
