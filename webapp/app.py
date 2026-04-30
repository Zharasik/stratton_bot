from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("WEBAPP_SECRET_KEY", "change-me-in-production")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
# Fallback password for non-Telegram access (optional, set WEBAPP_PASSWORD= to disable)
WEBAPP_PASSWORD = os.getenv("WEBAPP_PASSWORD", "")

_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/stratton_bot.db")
_DB_PATH = _DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")

NDA_FIELDS = [
    ("last_name", "Фамилия"),
    ("first_name", "Имя"),
    ("middle_name", "Отчество"),
    ("iin", "ИИН"),
    ("doc_number", "Номер документа"),
    ("birth_date", "Дата рождения"),
    ("doc_expiry", "Срок действия"),
    ("issuing_authority", "Орган выдачи"),
    ("nationality", "Национальность"),
    ("birth_place", "Место рождения"),
    ("phone", "Телефон"),
    ("email", "Email"),
    ("address", "Адрес"),
    ("status", "Статус"),
]


def _db() -> sqlite3.Connection:
    db_path = Path(_DB_PATH)
    if not db_path.is_absolute():
        db_path = Path(__file__).parent.parent / db_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _validate_init_data(init_data: str) -> dict | None:
    """Validate Telegram Web App initData. Returns parsed user dict or None."""
    if not BOT_TOKEN or not init_data:
        return None
    try:
        params = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = params.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return None
        return json.loads(params.get("user", "{}"))
    except Exception:
        return None


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Auth: Telegram initData (called by JS on page load) ─────────────────────

@app.route("/tg-auth", methods=["POST"])
def tg_auth():
    init_data = request.json.get("initData", "") if request.is_json else ""
    user = _validate_init_data(init_data)
    if user and _is_admin(user.get("id", 0)):
        session["authenticated"] = True
        session["user_id"] = user["id"]
        session["username"] = user.get("username", "")
        return {"ok": True}
    return {"ok": False, "error": "Нет доступа"}, 403


# ── Auth: password fallback ──────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if WEBAPP_PASSWORD and request.form.get("password") == WEBAPP_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        flash("Неверный пароль")
    # If opened from Telegram, JS will auto-authenticate via /tg-auth
    return render_template("login.html", password_enabled=bool(WEBAPP_PASSWORD))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Main views ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    query = request.args.get("q", "").strip()
    with _db() as conn:
        if query:
            like = f"%{query}%"
            rows = conn.execute(
                """
                SELECT n.*, u.full_name, u.username
                FROM nda_records n
                LEFT JOIN users u ON n.user_id = u.user_id
                WHERE n.iin LIKE ? OR n.last_name LIKE ? OR n.first_name LIKE ?
                   OR n.middle_name LIKE ? OR n.phone LIKE ? OR n.email LIKE ?
                ORDER BY n.created_at DESC
                """,
                (like, like, like, like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT n.*, u.full_name, u.username
                FROM nda_records n
                LEFT JOIN users u ON n.user_id = u.user_id
                ORDER BY n.created_at DESC
                """,
            ).fetchall()
    return render_template("index.html", records=rows, query=query)


@app.route("/nda/<int:nda_id>", methods=["GET", "POST"])
@login_required
def edit(nda_id: int):
    with _db() as conn:
        if request.method == "POST":
            updates = {
                field: request.form.get(field, "").strip() or None
                for field, _ in NDA_FIELDS
            }
            placeholders = ", ".join(f"{f} = ?" for f, _ in NDA_FIELDS)
            values = [updates[f] for f, _ in NDA_FIELDS] + [nda_id]
            conn.execute(
                f"UPDATE nda_records SET {placeholders} WHERE id = ?",  # noqa: S608
                values,
            )
            conn.commit()
            flash("Данные сохранены")
            return redirect(url_for("edit", nda_id=nda_id))

        row = conn.execute(
            """
            SELECT n.*, u.full_name, u.username
            FROM nda_records n
            LEFT JOIN users u ON n.user_id = u.user_id
            WHERE n.id = ?
            """,
            (nda_id,),
        ).fetchone()

    if row is None:
        flash("Запись не найдена")
        return redirect(url_for("index"))

    return render_template("edit.html", record=row, fields=NDA_FIELDS)


if __name__ == "__main__":
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
