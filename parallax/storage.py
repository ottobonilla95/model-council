import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

from . import config


class CapacityError(ValueError):
    pass


class SessionBusyError(ValueError):
    pass


class LeaseLostError(RuntimeError):
    pass


class OwnershipError(ValueError):
    pass


def now():
    return datetime.now(UTC).isoformat()


@contextmanager
def connection():
    url = config.database_url()
    if url:
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(url, row_factory=dict_row, connect_timeout=10, prepare_threshold=None) as db:
            yield db
    else:
        if config.hosted():
            raise RuntimeError("DATABASE_URL is required on Vercel; local storage is disabled.")
        config.DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(config.DATA / "parallax.sqlite3", timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()


def query(db, sql, args=()):
    # Queries below use only placeholders, never question marks in SQL literals.
    return db.execute(sql.replace("?", "%s") if config.database_url() else sql, args)


def init():
    with connection() as db:
        postgres = bool(config.database_url())
        if postgres:
            # Concurrent cold starts must not race schema creation.
            query(db, "SELECT pg_advisory_xact_lock(721093412)")
        event_id = "BIGSERIAL PRIMARY KEY" if postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        statements = [
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, created TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created TEXT NOT NULL, "
            "status TEXT NOT NULL, request TEXT NOT NULL, result TEXT, job_token TEXT, lease_until DOUBLE PRECISION)",
            f"CREATE TABLE IF NOT EXISTS events (id {event_id}, run_id TEXT NOT NULL, created TEXT NOT NULL, payload TEXT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS events_run ON events(run_id,id)",
            "CREATE INDEX IF NOT EXISTS runs_session ON runs(session_id,created)",
        ]
        for sql in statements:
            query(db, sql)
        if postgres:
            query(db, "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS owner_id TEXT")
        elif "owner_id" not in {r["name"] for r in query(db, "PRAGMA table_info(sessions)")}:
            query(db, "ALTER TABLE sessions ADD COLUMN owner_id TEXT")
        query(db, "CREATE INDEX IF NOT EXISTS sessions_owner ON sessions(owner_id,created)")
        from .accounts import init_tables
        from .memory import init_tables as init_memory

        init_tables(db)
        # Older releases assigned anonymous conversations to the owner. A session
        # predating its assigned account could not have been created by that account.
        query(
            db,
            "UPDATE sessions SET owner_id=NULL WHERE EXISTS ("
            "SELECT 1 FROM users WHERE users.id=sessions.owner_id AND sessions.created<users.created)",
        )
        init_memory(db)
        if postgres:
            for name, kind in (("job_token", "TEXT"), ("lease_until", "DOUBLE PRECISION")):
                query(db, f"ALTER TABLE runs ADD COLUMN IF NOT EXISTS {name} {kind}")
        else:
            columns = {r["name"] for r in query(db, "PRAGMA table_info(runs)")}
            for name, kind in (("job_token", "TEXT"), ("lease_until", "DOUBLE PRECISION")):
                if name not in columns:
                    query(db, f"ALTER TABLE runs ADD COLUMN {name} {kind}")
        if not config.hosted():
            interrupted = query(db, "SELECT id FROM runs WHERE status='running'").fetchall()
            for row in interrupted:
                query(db, "UPDATE runs SET status='interrupted' WHERE id=?", (row["id"],))
                query(
                    db,
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


def create_run(request, owner_id=None):
    session = request.session_id or uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    with connection() as db:
        if config.database_url():
            query(db, "SELECT pg_advisory_xact_lock(721093413)")
        else:
            query(db, "BEGIN IMMEDIATE")
        existing = query(db, "SELECT owner_id FROM sessions WHERE id=?", (session,)).fetchone()
        if existing and existing["owner_id"] != owner_id:
            raise OwnershipError("Conversation not found.")
        if query(db, "SELECT COUNT(*) AS n FROM runs WHERE status='running'").fetchone()["n"] >= 2:
            raise CapacityError("Two rounds are already running. Stop one or wait for it to finish.")
        if query(db, "SELECT id FROM runs WHERE session_id=? AND status='running'", (session,)).fetchone():
            raise SessionBusyError("Wait for this conversation's current round to finish.")
        query(
            db,
            "INSERT INTO sessions(id,title,created,owner_id) VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING",
            (session, request.question[:90], now(), owner_id),
        )
        query(
            db,
            "INSERT INTO runs(id,session_id,created,status,request) VALUES(?,?,?,?,?)",
            (run_id, session, now(), "running", request.model_dump_json()),
        )
    return run_id, session


def event(run_id, payload, token=None):
    with connection() as db:
        if token:
            cursor = query(
                db,
                "INSERT INTO events(run_id,created,payload) SELECT id,?,? FROM runs "
                "WHERE id=? AND status='running' AND job_token=? RETURNING id",
                (now(), json.dumps(payload), run_id, token),
            )
        else:
            cursor = query(
                db, "INSERT INTO events(run_id,created,payload) VALUES(?,?,?) RETURNING id", (run_id, now(), json.dumps(payload))
            )
        row = cursor.fetchone()
        if not row:
            raise LeaseLostError("Research ownership changed or the round was stopped.")
        return row["id"]


def finish(run_id, status, result=None, token=None, terminal=None, unleased=False):
    with connection() as db:
        sql = "UPDATE runs SET status=?,result=? WHERE id=? AND status='running'"
        args = [status, json.dumps(result) if result else None, run_id]
        if token:
            sql += " AND job_token=?"
            args.append(token)
        if unleased:
            sql += " AND lease_until IS NULL"
        changed = query(db, sql + " RETURNING id", args).fetchone()
        if changed and terminal:
            query(db, "INSERT INTO events(run_id,created,payload) VALUES(?,?,?)", (run_id, now(), json.dumps(terminal)))
        return bool(changed)


def claim(run_id, token):
    with connection() as db:
        return bool(
            query(
                db,
                "UPDATE runs SET job_token=?,lease_until=? WHERE id=? AND status='running' "
                "AND (lease_until IS NULL OR lease_until<?) RETURNING id",
                (token, time.time() + 60, run_id, time.time()),
            ).fetchone()
        )


def renew(run_id, token):
    with connection() as db:
        return bool(
            query(
                db,
                "UPDATE runs SET lease_until=? WHERE id=? AND job_token=? AND status='running' RETURNING id",
                (time.time() + 60, run_id, token),
            ).fetchone()
        )


def release(run_id, token):
    with connection() as db:
        query(db, "UPDATE runs SET lease_until=NULL WHERE id=? AND job_token=?", (run_id, token))


def expire_abandoned():
    # A queue message lives for an hour. Never leave its UI spinning indefinitely.
    cutoff = datetime.fromtimestamp(time.time() - 3900, UTC).isoformat()
    with connection() as db:
        rows = query(
            db,
            "UPDATE runs SET status='interrupted' WHERE status='running' AND created<? "
            "AND (lease_until IS NULL OR lease_until<?) RETURNING id",
            (cutoff, time.time()),
        ).fetchall()
        for row in rows:
            query(
                db,
                "INSERT INTO events(run_id,created,payload) VALUES(?,?,?)",
                (
                    row["id"],
                    now(),
                    json.dumps(
                        {
                            "type": "interrupted",
                            "message": "The research job expired. Saved answers are available; start a new round to continue.",
                        }
                    ),
                ),
            )


def unpack(row):
    if row is None:
        return None
    result = dict(row)
    result.pop("job_token", None)
    result.pop("lease_until", None)
    for key in ("request", "result", "payload"):
        if result.get(key):
            result[key] = json.loads(result[key])
    return result


def get_run(run_id):
    with connection() as db:
        return unpack(query(db, "SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())


def events(run_id, after=0):
    with connection() as db:
        return [unpack(row) for row in query(db, "SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after))]


def owns_session(session_id, owner_id):
    with connection() as db:
        row = query(db, "SELECT owner_id FROM sessions WHERE id=?", (session_id,)).fetchone()
        return bool(row and row["owner_id"] == owner_id)


def sessions(owner_id=None):
    with connection() as db:
        return [
            dict(row)
            for row in query(
                db,
                "SELECT s.id,s.title,s.created,MAX(r.created) AS updated,COUNT(r.id) AS rounds "
                "FROM sessions s JOIN runs r ON s.id=r.session_id "
                + ("WHERE s.owner_id IS NULL " if owner_id is None else "WHERE s.owner_id=? ")
                + "GROUP BY s.id,s.title,s.created ORDER BY updated DESC",
                () if owner_id is None else (owner_id,),
            )
        ]


def session_runs(session_id):
    with connection() as db:
        return [unpack(row) for row in query(db, "SELECT * FROM runs WHERE session_id=? ORDER BY created", (session_id,))]


def completed_reports(run_id):
    reports = {}
    for item in events(run_id):
        payload = item["payload"]
        if payload["type"] == "researcher_done":
            reports[payload["report"]["model"]] = payload["report"]
    return reports


def conversation_history(session_id, exclude_run=None):
    """The assistant sees the conversation; independent researchers keep their own history."""
    result = []
    for run in session_runs(session_id):
        if run["id"] == exclude_run or run["request"].get("demo"):
            continue
        saved = run.get("result") or {}
        answer = saved.get("answer") or (saved.get("comparison") or {}).get("answer")
        if answer:
            result.extend(
                [
                    {"role": "user", "content": run["request"]["question"]},
                    {"role": "assistant", "content": answer[:12000]},
                ]
            )
    return result[-12:]


def research_history(session_id, model, exclude_run=None):
    """Only user turns and this model's own findings; never the synthesis/siblings."""
    result = []
    for run in session_runs(session_id):
        if run["id"] == exclude_run or run["request"].get("demo"):
            continue
        result.append({"role": "user", "content": run["request"]["question"]})
        reports = (run.get("result") or {}).get("reports", []) or list(completed_reports(run["id"]).values())
        own = next((r for r in reports if r["model"] == model), None)
        if own and own.get("answer"):
            result.append({"role": "assistant", "content": own["answer"][:18000]})
    return result[-8:]
