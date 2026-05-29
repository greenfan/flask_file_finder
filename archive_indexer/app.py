from __future__ import annotations

import threading
import time
from pathlib import Path
import sys

from flask import Flask, jsonify, render_template, request

if __package__ in {None, ""}:
    _pkg_root = Path(__file__).resolve().parents[1]
    if str(_pkg_root) not in sys.path:
        sys.path.insert(0, str(_pkg_root))
    from archive_indexer.db import ArchiveDB
    from archive_indexer.scanner import scan_directory
else:
    from .db import ArchiveDB
    from .scanner import scan_directory


def _human_ts(value):
    if not value:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))


def create_app(db_path: str | Path | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    db = ArchiveDB(db_path)
    state = {
        "running": False,
        "root": None,
        "mode": None,
        "started_at": None,
        "finished_at": None,
        "message": "idle",
        "result": None,
    }
    lock = threading.Lock()

    def status_snapshot():
        snap = dict(state)
        if snap.get("started_at"):
            snap["started_at_human"] = _human_ts(snap["started_at"])
        if snap.get("finished_at"):
            snap["finished_at_human"] = _human_ts(snap["finished_at"])
        return snap

    def progress_cb(event: str, payload: dict):
        with lock:
            if event == "started":
                state["running"] = True
                state["root"] = payload.get("root")
                state["started_at"] = payload.get("started_at")
                state["mode"] = payload.get("mode")
                state["message"] = "scan started"
            elif event == "progress":
                state["message"] = f"scanned {payload.get('files_seen', 0)} files"
            elif event == "updated":
                state["message"] = f"updated {payload.get('files_updated', 0)} records"
            elif event == "error":
                state["message"] = f"error: {payload.get('path')}"
            elif event == "stale_removed":
                state["message"] = f"removed {payload.get('count', 0)} stale entries"
            elif event == "nested":
                state["message"] = f"nested: {payload.get('path')}"
            elif event == "finished":
                state["running"] = False
                state["finished_at"] = payload.get("finished_at")
                state["result"] = payload
                state["message"] = "scan complete"

    def launch_scan(root: str, *, include_nested: bool = False, force: bool = False):
        with lock:
            if state["running"]:
                return False, "scan already running"
            state["running"] = True
            state["root"] = root
            state["mode"] = "force" if force else "incremental"
            state["started_at"] = time.time()
            state["finished_at"] = None
            state["message"] = "launching scan"

        def worker():
            try:
                scan_directory(root, db, include_nested=include_nested, force=force, progress_cb=progress_cb)
            except Exception as exc:
                with lock:
                    state["running"] = False
                    state["finished_at"] = time.time()
                    state["message"] = f"failed: {exc}"
                    state["result"] = {"error": str(exc)}

        threading.Thread(target=worker, daemon=True).start()
        return True, "started"

    @app.route("/")
    def index():
        stats = db.stats()
        return render_template("index.html", stats=stats, status=status_snapshot(), default_root=request.args.get("root", ""), _human_ts=_human_ts)

    @app.route("/archives")
    def archives():
        q = request.args.get("q") or None
        sort = request.args.get("sort", "mtime")
        rows = db.list_archives(q=q, sort=sort, limit=int(request.args.get("limit", 500)), offset=int(request.args.get("offset", 0)))
        return render_template("archives.html", rows=rows, q=q or "", sort=sort, _human_ts=_human_ts)

    @app.route("/errors")
    def errors():
        rows = db.list_errors(limit=int(request.args.get("limit", 500)), offset=int(request.args.get("offset", 0)))
        return render_template("errors.html", rows=rows, _human_ts=_human_ts)

    @app.route("/scan", methods=["POST"])
    def scan():
        payload = request.get_json(silent=True) if request.is_json else request.form
        root = payload.get("root") if payload else None
        include_nested = bool(payload.get("include_nested")) if payload else False
        if not root:
            return jsonify({"ok": False, "error": "root is required"}), 400
        ok, message = launch_scan(root, include_nested=include_nested, force=False)
        return jsonify({"ok": ok, "message": message, "status": status_snapshot()}), (202 if ok else 409)

    @app.route("/rescan", methods=["POST"])
    def rescan():
        payload = request.get_json(silent=True) if request.is_json else request.form
        root = payload.get("root") if payload else None
        include_nested = bool(payload.get("include_nested")) if payload else False
        if not root:
            return jsonify({"ok": False, "error": "root is required"}), 400
        ok, message = launch_scan(root, include_nested=include_nested, force=True)
        return jsonify({"ok": ok, "message": message, "status": status_snapshot()}), (202 if ok else 409)

    @app.route("/api/archives")
    def api_archives():
        q = request.args.get("q") or None
        sort = request.args.get("sort", "mtime")
        rows = db.list_archives(q=q, sort=sort, limit=int(request.args.get("limit", 500)), offset=int(request.args.get("offset", 0)))
        return jsonify([dict(row) for row in rows])

    @app.route("/api/errors")
    def api_errors():
        rows = db.list_errors(limit=int(request.args.get("limit", 500)), offset=int(request.args.get("offset", 0)))
        return jsonify([dict(row) for row in rows])

    @app.route("/api/stats")
    def api_stats():
        payload = db.stats()
        payload["status"] = status_snapshot()
        return jsonify(payload)

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True, "status": status_snapshot(), "stats": db.stats()})

    return app


def main(host: str = "0.0.0.0", port: int = 19000, db_path: str | Path | None = None, debug: bool = False):
    app = create_app(db_path=db_path)
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    raise SystemExit(main())
