from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import parse_qsl

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, send_file, session, url_for

# Load .env from project root regardless of working directory
load_dotenv(Path(__file__).parent.parent / ".env")

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.secret_key = os.getenv("WEBAPP_SECRET_KEY", "change-me-in-production")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
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


def _notify_user(user_id: int, text: str) -> None:
    """Send a Telegram message to a user via Bot API (fire-and-forget)."""
    if not BOT_TOKEN:
        return
    try:
        payload = json.dumps({"chat_id": user_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # best-effort, don't break the web request


_STATUS_MESSAGES = {
    "pending":   "📋 Ваш NDA требует доработки. Пожалуйста, проверьте и исправьте данные.",
    "completed": "✅ Ваш NDA подтверждён!",
    "cancelled": "❌ Ваш NDA отменён. Отправьте фото удостоверения для повторного заполнения.",
}


def _nda_file_path(row) -> Path | None:
    """Return the path to the generated NDA docx, or None if not found."""
    root = Path(__file__).parent.parent
    for candidate in (
        root / "data" / f"nda_{row['iin']}.docx",
        root / "data" / f"nda_{row['user_id']}.docx",
    ):
        if candidate.exists():
            return candidate
    return None


def login_required(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


# ── Auth: Telegram initData ──────────────────────────────────────────────────

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
    rows = []
    try:
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
    except sqlite3.OperationalError as e:
        flash(f"Ошибка базы данных: {e}")
    return render_template("index.html", records=rows, query=query)


@app.route("/download/<int:nda_id>")
@login_required
def download_nda(nda_id: int):
    with _db() as conn:
        row = conn.execute("SELECT * FROM nda_records WHERE id = ?", (nda_id,)).fetchone()
    if row is None:
        flash("Запись не найдена")
        return redirect(url_for("index"))
    path = _nda_file_path(row)
    if path is None:
        flash("Файл NDA ещё не сформирован")
        return redirect(url_for("edit", nda_id=nda_id))
    name = f"NDA_{row['last_name'] or row['user_id']}.docx"
    return send_file(path, as_attachment=True, download_name=name)


@app.route("/nda/<int:nda_id>", methods=["GET", "POST"])
@login_required
def edit(nda_id: int):
    with _db() as conn:
        if request.method == "POST":
            old_row = conn.execute(
                "SELECT status, user_id FROM nda_records WHERE id = ?", (nda_id,)
            ).fetchone()
            old_status = old_row["status"] if old_row else None

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

            # Notify user if status changed
            new_status = updates.get("status")
            if old_row and new_status and new_status != old_status:
                msg = _STATUS_MESSAGES.get(new_status)
                if msg:
                    _notify_user(old_row["user_id"], msg)

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


# ── User-facing form (opened from bot link) ──────────────────────────────────

NDA_FORM_FIELDS = [
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
]


def _make_form_token(nda_id: int, user_id: int) -> str:
    secret = app.secret_key if isinstance(app.secret_key, bytes) else app.secret_key.encode()
    msg = f"{nda_id}:{user_id}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


def _verify_form_token(token: str, nda_id: int, user_id: int) -> bool:
    return hmac.compare_digest(token, _make_form_token(nda_id, user_id))


@app.route("/form/<int:nda_id>", methods=["GET", "POST"])
def form(nda_id: int):
    with _db() as conn:
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
        return render_template("form_error.html", message="Запись не найдена"), 404

    # Token in URL grants access (generated by bot with WEBAPP_SECRET_KEY)
    token = request.args.get("token", "")
    if token and _verify_form_token(token, nda_id, row["user_id"]):
        session["form_user_id"] = row["user_id"]
        # Redirect to clean URL without token in address bar
        return redirect(url_for("form", nda_id=nda_id))

    # Check session (set after token redirect or admin login)
    is_admin = session.get("authenticated")
    is_owner = session.get("form_user_id") == row["user_id"]
    if not (is_admin or is_owner):
        return render_template("form_error.html", message="Ссылка недействительна. Получите новую ссылку в боте через /mynda."), 403

    if request.method == "POST":
        with _db() as conn:
            updates = {
                field: request.form.get(field, "").strip() or None
                for field, _ in NDA_FORM_FIELDS
            }
            placeholders = ", ".join(f"{f} = ?" for f, _ in NDA_FORM_FIELDS)
            values = [updates[f] for f, _ in NDA_FORM_FIELDS] + [nda_id]
            conn.execute(
                f"UPDATE nda_records SET {placeholders} WHERE id = ?",  # noqa: S608
                values,
            )
            conn.commit()
        return render_template("form_saved.html")

    return render_template("form.html", record=row, fields=NDA_FORM_FIELDS)


if __name__ == "__main__":
    port = int(os.getenv("WEBAPP_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "0") == "1")
