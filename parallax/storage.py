import json
import sqlite3
import uuid
from datetime import UTC, datetime

from . import config


def now():
    return datetime.now(UTC).isoformat()


def connection():
    config.DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(config.DATA / "parallax.sqlite3", timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created TEXT NOT NULL,
          status TEXT NOT NULL, request TEXT NOT NULL, result TEXT);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          created TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id);
        CREATE INDEX IF NOT EXISTS runs_session ON runs(session_id,created);
        """)
        interrupted = db.execute("SELECT id FROM runs WHERE status='running'").fetchall()
        for row in interrupted:
            db.execute("UPDATE runs SET status='interrupted' WHERE id=?", (row["id"],))
            db.execute(
                "INSERT INTO events(run_id,created,payload) VALUES(?,?,?)",
                (
                    row["id"],
                    now(),
                    json.dumps(
                        {
                            "type": "interrupted",
                            "message": "Server restarted. Saved research is still available; start a new round to continue.",
                        }
                    ),
                ),
            )


def create_run(request):
    session = request.session_id or uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    with connection() as db:
        db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?,?)", (session, request.question[:90], now()))
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?,NULL)", (run_id, session, now(), "running", request.model_dump_json()))
    return run_id, session


def event(run_id, payload):
    with connection() as db:
        cursor = db.execute("INSERT INTO events(run_id,created,payload) VALUES(?,?,?)", (run_id, now(), json.dumps(payload)))
    return cursor.lastrowid


def finish(run_id, status, result=None):
    with connection() as db:
        db.execute("UPDATE runs SET status=?,result=? WHERE id=?", (status, json.dumps(result) if result else None, run_id))


def unpack(row):
    if row is None:
        return None
    result = dict(row)
    for key in ("request", "result", "payload"):
        if result.get(key):
            result[key] = json.loads(result[key])
    return result


def get_run(run_id):
    with connection() as db:
        return unpack(db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())


def events(run_id, after=0):
    with connection() as db:
        return [unpack(row) for row in db.execute("SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after))]


def sessions():
    with connection() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT s.*, MAX(r.created) AS updated, COUNT(r.id) AS rounds FROM sessions s JOIN runs r ON s.id=r.session_id GROUP BY s.id ORDER BY updated DESC"
            )
        ]


def session_runs(session_id):
    with connection() as db:
        return [unpack(row) for row in db.execute("SELECT * FROM runs WHERE session_id=? ORDER BY created", (session_id,))]


def research_history(session_id, model):
    """Only user turns and this model's own findings; never the synthesis/siblings."""
    result = []
    for run in session_runs(session_id):
        if run["request"].get("demo"):
            continue
        result.append({"role": "user", "content": run["request"]["question"]})
        reports = (run.get("result") or {}).get("reports", [])
        if not reports:
            reports = [e["payload"]["report"] for e in events(run["id"]) if e["payload"]["type"] == "researcher_done"]
        own = next((r for r in reports if r["model"] == model), None)
        if own and own.get("answer"):
            result.append({"role": "assistant", "content": own["answer"][:18000]})
    return result[-8:]
