"""Account persistence and revocable, opaque browser sessions. No Google tokens are retained."""

import hashlib
import json
import os
import secrets
import time
import uuid

from . import storage

SESSION_SECONDS = 30 * 24 * 60 * 60


def init_tables(db):
    for sql in (
        "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, google_sub TEXT UNIQUE, email TEXT UNIQUE NOT NULL, "
        "name TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL, last_login TEXT)",
        "CREATE TABLE IF NOT EXISTS login_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL)",
        "CREATE INDEX IF NOT EXISTS login_sessions_user ON login_sessions(user_id)",
    ):
        storage.query(db, sql)


def owner_email():
    return os.getenv("PARALLAX_OWNER_EMAIL", "").strip().lower()


def public_user(row):
    return {k: row[k] for k in ("id", "email", "name", "role", "active", "created", "last_login")}


def lock(db):
    if storage.config.database_url():
        storage.query(db, "SELECT pg_advisory_xact_lock(721093414)")
    else:
        storage.query(db, "BEGIN IMMEDIATE")


def from_google(info):
    # Only the OIDC library's signature/issuer/audience/nonce-validated userinfo enters here.
    email = str(info.get("email", "")).strip().lower()
    subject = str(info.get("sub", ""))
    if info.get("email_verified") is not True or not email or not subject:
        raise ValueError("Google must verify your email address before you can sign in.")
    # Gmail is authoritative for Gmail addresses. For non-Gmail accounts Google must
    # assert a Workspace domain; an old email_verified claim alone is insufficient.
    if not email.endswith("@gmail.com") and not info.get("hd"):
        raise ValueError("Use a Gmail or Google Workspace account with a verified email address.")
    with storage.connection() as db:
        lock(db)
        row = storage.query(db, "SELECT * FROM users WHERE google_sub=?", (subject,)).fetchone()
        if not row:
            row = storage.query(db, "SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if row and row["google_sub"]:
                raise ValueError("That email is already linked to another Google account.")
        if row and not row["active"]:
            raise ValueError("This account is disabled. Contact the Parallax administrator.")
        stamp = storage.now()
        if not row:
            if os.getenv("PARALLAX_ALLOW_SIGNUP", "1") != "1" and email != owner_email():
                raise ValueError("Ask the Parallax administrator to create your account first.")
            user_id = uuid.uuid4().hex
            storage.query(
                db,
                "INSERT INTO users(id,google_sub,email,name,role,active,created,last_login) VALUES(?,?,?,?,?,1,?,?)",
                (
                    user_id,
                    subject,
                    email,
                    str(info.get("name") or email)[:120],
                    "admin" if email == owner_email() else "user",
                    stamp,
                    stamp,
                ),
            )
        else:
            user_id = row["id"]
            storage.query(db, "UPDATE users SET google_sub=?,last_login=? WHERE id=?", (subject, stamp, user_id))
        if email == owner_email():
            storage.query(db, "UPDATE users SET role='admin' WHERE id=?", (user_id,))
        row = storage.query(db, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if email == owner_email():
            # Existing anonymous conversations belong only to the explicitly configured
            # owner, never whichever person happens to register first.
            storage.query(db, "UPDATE sessions SET owner_id=? WHERE owner_id IS NULL", (user_id,))
        return public_user(row)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token):
    return digest("parallax-csrf:" + token)


def new_session(user_id):
    token = secrets.token_urlsafe(48)
    with storage.connection() as db:
        storage.query(db, "DELETE FROM login_sessions WHERE expires<?", (time.time(),))
        storage.query(db, "INSERT INTO login_sessions VALUES(?,?,?)", (digest(token), user_id, time.time() + SESSION_SECONDS))
    return token


def session_user(token):
    if not token or len(token) > 200:
        return None
    with storage.connection() as db:
        row = storage.query(
            db,
            "SELECT u.* FROM login_sessions l JOIN users u ON u.id=l.user_id WHERE l.token_hash=? AND l.expires>? AND u.active=1",
            (digest(token), time.time()),
        ).fetchone()
        return public_user(row) if row else None


def revoke_session(token):
    with storage.connection() as db:
        storage.query(db, "DELETE FROM login_sessions WHERE token_hash=?", (digest(token),))


def list_users():
    with storage.connection() as db:
        return [public_user(row) for row in storage.query(db, "SELECT * FROM users ORDER BY created DESC")]


def create_user(email, name):
    with storage.connection() as db:
        lock(db)
        if storage.query(db, "SELECT id FROM users WHERE email=?", (email,)).fetchone():
            raise ValueError("An account already exists with that email.")
        user_id = uuid.uuid4().hex
        storage.query(
            db,
            "INSERT INTO users(id,email,name,role,active,created) VALUES(?,?,?,'user',1,?)",
            (user_id, email, name or email, storage.now()),
        )
        return public_user(storage.query(db, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def update_user(user_id, actor_id, role, active):
    with storage.connection() as db:
        lock(db)
        row = storage.query(db, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise LookupError("User not found.")
        if user_id == actor_id or row["email"] == owner_email():
            raise ValueError("You cannot change your own access or the owner's access.")
        storage.query(db, "UPDATE users SET role=?,active=? WHERE id=?", (role, int(active), user_id))
        # Changing access revokes existing sessions even if the user is later re-enabled.
        storage.query(db, "DELETE FROM login_sessions WHERE user_id=?", (user_id,))
        if not active:
            stopped = storage.query(
                db,
                "UPDATE runs SET status='cancelled' WHERE status='running' AND session_id IN "
                "(SELECT id FROM sessions WHERE owner_id=?) RETURNING id",
                (user_id,),
            ).fetchall()
            for run in stopped:
                storage.query(
                    db,
                    "INSERT INTO events(run_id,created,payload) VALUES(?,?,?)",
                    (run["id"], storage.now(), json.dumps({"type": "cancelled", "message": "Account access was disabled."})),
                )
        return public_user(storage.query(db, "SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
