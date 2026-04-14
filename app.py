from flask import Flask, jsonify, request, send_from_directory, session, make_response
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from functools import wraps
from io import BytesIO
import os

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "billr.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=".")
app.secret_key = os.getenv("APP_SECRET", "change-me-in-production")

DEFAULT_USERNAME = os.getenv("APP_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("APP_PASSWORD", "admin123")

DEFAULT_STATE = {
    "rate": 0,
    "monthlyGoal": 5000,
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT id FROM app_state WHERE id = 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO app_state (id, state_json, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_STATE), datetime.now(timezone.utc).isoformat()),
            )

        user = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USERNAME,)).fetchone()
        if user is None:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (
                    DEFAULT_USERNAME,
                    generate_password_hash(DEFAULT_PASSWORD),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return jsonify({"error": "unauthorized"}), 401
        return fn(*args, **kwargs)

    return wrapper


def get_state_value():
    with get_conn() as conn:
        row = conn.execute("SELECT state_json FROM app_state WHERE id = 1").fetchone()
        if row is None:
            return DEFAULT_STATE
        return json.loads(row["state_json"])


@app.route("/")
def root():
    return send_from_directory(APP_DIR, "index.html")


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "")
    password = payload.get("password", "")
    with get_conn() as conn:
        row = conn.execute("SELECT username, password_hash FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return jsonify({"ok": False, "error": "Invalid username or password"}), 401
    session["user"] = username
    return jsonify({"ok": True, "user": username})


@app.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me", methods=["GET"])
def me():
    user = session.get("user")
    return jsonify({"authenticated": bool(user), "user": user})


@app.route("/api/state", methods=["GET"])
@require_auth
def get_state():
    with get_conn() as conn:
        row = conn.execute("SELECT state_json, updated_at FROM app_state WHERE id = 1").fetchone()
        if row is None:
            return jsonify({"state": DEFAULT_STATE, "updated_at": None})
        return jsonify({"state": json.loads(row["state_json"]), "updated_at": row["updated_at"]})


@app.route("/api/state", methods=["PUT"])
@require_auth
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


@app.route("/api/invoices/<int:invoice_id>/pdf", methods=["GET"])
@require_auth
def invoice_pdf(invoice_id: int):
    state = get_state_value()
    invoices = state.get("invoices", [])
    logs = state.get("logs", [])
    clients = state.get("clients", [])

    inv = next((i for i in invoices if i.get("id") == invoice_id), None)
    if not inv:
        return jsonify({"error": "Invoice not found"}), 404

    client = next((c for c in clients if c.get("id") == inv.get("clientId")), {"name": "Unknown Client"})
    entries = [l for l in logs if l.get("id") in inv.get("entryIds", [])]

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    y = height - 50
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "INVOICE")
    y -= 30

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Invoice #: {inv.get('number', '')}")
    y -= 18
    pdf.drawString(50, y, f"Date: {inv.get('date', '')}")
    y -= 18
    pdf.drawString(50, y, f"Client: {client.get('name', 'Unknown Client')}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Date")
    pdf.drawString(130, y, "Description")
    pdf.drawString(420, y, "Amount")
    y -= 12
    pdf.line(50, y, 550, y)
    y -= 18

    pdf.setFont("Helvetica", 10)
    for item in entries:
        desc = (item.get("desc") or "")[:55]
        pdf.drawString(50, y, item.get("date", ""))
        pdf.drawString(130, y, desc)
        pdf.drawRightString(530, y, f"${float(item.get('amount', 0)):.2f}")
        y -= 16
        if y < 100:
            pdf.showPage()
            y = height - 50

    y -= 10
    pdf.line(380, y, 550, y)
    y -= 20
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(400, y, "Total")
    pdf.drawRightString(530, y, f"${float(inv.get('total', 0)):.2f}")
    y -= 30

    notes = inv.get("notes") or ""
    if notes:
        pdf.setFont("Helvetica", 10)
        pdf.drawString(50, y, "Notes:")
        y -= 16
        for line in [notes[i : i + 90] for i in range(0, len(notes), 90)]:
            pdf.drawString(50, y, line)
            y -= 14

    pdf.save()
    buf.seek(0)

    response = make_response(buf.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename={inv.get('number', 'invoice')}.pdf"
    return response


@app.route("/<path:path>")
def static_proxy(path: str):
    return send_from_directory(APP_DIR, path)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=2555, debug=False)
