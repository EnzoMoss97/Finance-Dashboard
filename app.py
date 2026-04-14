from flask import Flask, jsonify, request, send_from_directory
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "billr.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=".")

DEFAULT_STATE = {
    "rate": 0,
    "clients": [],
    "projects": [],
    "logs": [],
    "invoices": [],
    "nextId": 1,
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT id FROM app_state WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_state (id, state_json, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_STATE), datetime.now(timezone.utc).isoformat()),
            )


@app.route("/")
def root():
    return send_from_directory(APP_DIR, "index.html")


@app.route("/api/state", methods=["GET"])
def get_state():
    with get_conn() as conn:
        row = conn.execute("SELECT state_json, updated_at FROM app_state WHERE id = 1").fetchone()
        if row is None:
            return jsonify({"state": DEFAULT_STATE, "updated_at": None})
        return jsonify({"state": json.loads(row["state_json"]), "updated_at": row["updated_at"]})


@app.route("/api/state", methods=["PUT"])
def put_state():
    payload = request.get_json(silent=True) or {}
    state = payload.get("state")
    if not isinstance(state, dict):
        return jsonify({"error": "payload must include a JSON object at key 'state'"}), 400

    updated_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_state (id, state_json, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (json.dumps(state), updated_at),
        )
    return jsonify({"ok": True, "updated_at": updated_at})


@app.route("/<path:path>")
def static_proxy(path: str):
    return send_from_directory(APP_DIR, path)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=2555, debug=False)
