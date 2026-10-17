"""Портал школы: анонсы олимпиад, конкурсов и творческих разработок учителей."""
import calendar as pycal
import os
import re
import sqlite3
import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import db, mailer, security

SCHOOL_NAME = "МБОУ СОШ № 61 им. П. Е. Ладана"
SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-to-a-long-random-string")

app = FastAPI(title=f"Портал олимпиад и конкурсов — {SCHOOL_NAME}")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
)

APP_DIR = Path(__file__).resolve().parent
db.init_db()
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")

SUBJECTS = [
    "Математика", "Русский язык", "Литература", "Иностранный язык", "Физика",
    "Химия", "Биология", "История", "Обществознание", "География",
    "Информатика", "ОБЖ", "Музыка", "ИЗО", "Технология",
    "Физическая культура", "Другое",
]

KINDS = {
    "olympiad": "Олимпиада",
    "contest": "Конкурс",
    "development": "Творческая разработка",
    "event": "Мероприятие",
    "other": "Другое",
}

MAX_FILE_SIZE = 15 * 1024 * 1024  # 15 МБ на файл
SAFE_EXT = re.compile(r"^[A-Za-z0-9]{1,10}$")


# ---------------------------------------------------------------- утилиты

def get_conn() -> sqlite3.Connection:
    return db.get_conn()


def current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        return row
    finally:
        conn.close()


def render(request: Request, template: str, **ctx):
    user = current_user(request)
    base = dict(
        request=request,
        user=user,
        school=SCHOOL_NAME,
        flash=request.session.pop("flash", None),
        SUBJECTS=SUBJECTS,
        KINDS=KINDS,
        today=date.today().isoformat(),
    )
    base.update(ctx)
    return templates.TemplateResponse(template, base)


def set_flash(request: Request, text: str, level: str = "info") -> None:
    request.session["flash"] = (text, level)


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def require_teacher(request: Request):
    user = require_user(request)
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user


def require_admin(request: Request):
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Нужны права администратора")
    return user


def clean_link(link: str) -> str | None:
    link = (link or "").strip()
    if not link:
        return None
    if not link.startswith(("http://", "https://")):
        raise HTTPException(status_code=400,
                            detail="Ссылка должна начинаться с http:// или https://")
    return link


async def save_uploads(files: list[UploadFile], announcement_id: int) -> int:
    conn = get_conn()
    saved = 0
    try:
        for f in files:
            if not f.filename:
                continue
            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"Файл «{f.filename}» больше 15 МБ",
                )
            ext = Path(f.filename).suffix.lstrip(".")
            stored = f"{uuid.uuid4().hex}.{ext}" if SAFE_EXT.match(ext) else uuid.uuid4().hex
            (db.UPLOAD_DIR / stored).write_bytes(content)
            conn.execute(
                "INSERT INTO files (announcement_id, original_name, stored_name, size) "
                "VALUES (?, ?, ?, ?)",
                (announcement_id, Path(f.filename).name, stored, len(content)),
            )
            saved += 1
        conn.commit()
    finally:
        conn.close()
    return saved


# ---------------------------------------------------------------- страницы

@app.get("/")
def index(request: Request, q: str = "", subject: str = "", kind: str = "",
          active: str = "1"):
    conn = get_conn()
    try:
        sql = """
            SELECT a.*, u.full_name AS author,
                   (SELECT COUNT(*) FROM files f WHERE f.announcement_id = a.id) AS file_count
            FROM announcements a JOIN users u ON u.id = a.author_id
            WHERE a.status = 'approved'
        """
        params: list = []
        if q:
            sql += " AND (a.title LIKE ? OR a.description LIKE ?)"
            params += [f"%{q}%"] * 2
        if subject:
            sql += " AND a.subject = ?"
            params.append(subject)
        if kind:
            sql += " AND a.kind = ?"
            params.append(kind)
        if active == "1":
            sql += " AND (a.deadline IS NULL OR a.deadline >= date('now', 'localtime'))"
        sql += " ORDER BY COALESCE(a.deadline, '9999-12-31'), a.created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return render(request, "index.html", items=rows, q=q, subject=subject,
                  kind=kind, active=active)


@app.get("/calendar")
def calendar_page(request: Request, month: str = ""):
    today = date.today()
    try:
        year, mon = map(int, month.split("-"))
        cur = date(year, mon, 1)
    except (ValueError, AttributeError):
        cur = date(today.year, today.month, 1)
    prev_m = date(cur.year - (cur.month == 1), 12 if cur.month == 1 else cur.month - 1, 1)
    next_m = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    month_end = (next_m - timedelta(days=1)).isoformat()

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id, title, kind, subject, event_date, deadline
               FROM announcements
               WHERE status = 'approved' AND (
                     (event_date IS NOT NULL AND event_date BETWEEN ? AND ?)
                  OR (deadline IS NOT NULL AND deadline BETWEEN ? AND ?))""",
            (cur.isoformat(), month_end, cur.isoformat(), month_end),
        ).fetchall()
        upcoming = conn.execute(
            """SELECT id, title, kind, subject, event_date, deadline
               FROM announcements
               WHERE status = 'approved' AND event_date IS NOT NULL AND event_date >= ?
               ORDER BY event_date LIMIT 10""",
            (today.isoformat(),),
        ).fetchall()
    finally:
        conn.close()

    by_date: dict[str, list] = {}
    for r in rows:
        if r["event_date"]:
            by_date.setdefault(r["event_date"], []).append((r, "event"))
        if r["deadline"]:
            by_date.setdefault(r["deadline"], []).append((r, "deadline"))

    weeks = []
    for week in pycal.monthcalendar(cur.year, cur.month):
        cells = []
        for day in week:
            key = f"{cur.year}-{cur.month:02d}-{day:02d}" if day else ""
            cells.append({
                "day": day,
                "events": by_date.get(key, []) if day else [],
                "is_today": bool(day) and key == today.isoformat(),
            })
        weeks.append(cells)

    return render(request, "calendar.html", weeks=weeks, cur=cur,
                  prev=prev_m, next=next_m, upcoming=upcoming,
                  month_names=pycal.month_name, KINDS=KINDS)


@app.get("/announcement/{ann_id}")
def announcement_detail(request: Request, ann_id: int):
    conn = get_conn()
    try:
        item = conn.execute(
            """SELECT a.*, u.full_name AS author FROM announcements a
               JOIN users u ON u.id = a.author_id WHERE a.id = ?""",
            (ann_id,),
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        user = current_user(request)
        is_owner = bool(user) and user["id"] == item["author_id"]
        is_admin = bool(user) and user["role"] == "admin"
        if item["status"] != "approved" and not (is_owner or is_admin):
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        files = conn.execute(
            "SELECT * FROM files WHERE announcement_id = ?", (ann_id,)
        ).fetchall()
    finally:
        conn.close()
    return render(request, "announcement.html", item=item, files=files)


@app.get("/files/{file_id}")
def download_file(request: Request, file_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT f.*, a.status, a.author_id FROM files f
               JOIN announcements a ON a.id = f.announcement_id WHERE f.id = ?""",
            (file_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Файл не найден")
    user = current_user(request)
    allowed = row["status"] == "approved" or (
        user and (user["role"] == "admin" or user["id"] == row["author_id"])
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Файл не найден")
    path = db.UPLOAD_DIR / row["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Файл удалён с сервера")
    return FileResponse(path, filename=row["original_name"])


# ---------------------------------------------------------------- авторизация

@app.get("/login")
def login_page(request: Request):
    return render(request, "login.html", error=None)


@app.post("/login")
def login(request: Request, login_name: str = Form(...), password: str = Form(...)):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE login = ?", (login_name.strip(),)
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["is_active"] or not security.verify_password(password, row["password_hash"]):
        return render(request, "login.html", error="Неверный логин или пароль")
    request.session["user_id"] = row["id"]
    return RedirectResponse("/cabinet", status_code=303)


@app.get("/register")
def register_page(request: Request):
    return render(request, "register.html", error=None)


@app.post("/register")
def register(request: Request, login_name: str = Form(...), password: str = Form(...),
             password2: str = Form(...), full_name: str = Form(...),
             subject: str = Form(...)):
    login_name = login_name.strip()
    full_name = full_name.strip()
    error = None
    if len(login_name) < 3:
        error = "Логин — минимум 3 символа"
    elif len(password) < 6:
        error = "Пароль — минимус 6 символов"
    elif password != password2:
        error = "Пароли не совпадают"
    elif not full_name:
        error = "Укажите фамилию и имя"
    if error:
        return render(request, "register.html", error=error)
    conn = get_conn()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO users (login, password_hash, full_name, subject, role) "
                "VALUES (?, ?, ?, ?, 'teacher')",
                (login_name, security.hash_password(password), full_name, subject),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return render(request, "register.html",
                          error="Такой логин уже существует")
        request.session["user_id"] = cur.lastrowid
    finally:
        conn.close()
    return RedirectResponse("/cabinet", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------- подписка

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
CLASSES = [str(i) for i in range(5, 12)]


@app.get("/subscribe")
def subscribe_page(request: Request):
    return render(request, "subscribe.html", error=None, classes=CLASSES)


@app.post("/subscribe")
def subscribe(request: Request, email: str = Form(...),
              student_class: str = Form(...), subject: str = Form("")):
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return render(request, "subscribe.html", classes=CLASSES,
                      error="Проверьте адрес электронной почты")
    if student_class not in CLASSES:
        student_class = "5"
    token = uuid.uuid4().hex
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO subscribers (email, student_class, subject, token)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                 student_class = excluded.student_class,
                 subject = excluded.subject,
                 token = excluded.token""",
            (email, student_class, subject if subject in SUBJECTS else "", token),
        )
        conn.commit()
    finally:
        conn.close()
    set_flash(request, f"Готово! Подписка на «{email}» оформлена. "
                       "Вы получите письмо, когда появится новый анонс по выбранному предмету.")
    return RedirectResponse("/", status_code=303)


@app.get("/unsubscribe/{token}")
def unsubscribe(request: Request, token: str):
    conn = get_conn()
    try:
        row = conn.execute("SELECT email FROM subscribers WHERE token = ?",
                           (token,)).fetchone()
        conn.execute("DELETE FROM subscribers WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()
    set_flash(request,
              f"Подписка для {row['email']} отменена." if row else "Подписка уже отменена.",
              "warn")
    return RedirectResponse("/", status_code=303)


def notify_new_announcement(request: Request, ann_id: int) -> tuple[int, int]:
    """Письма подписчикам о новом анонсе. Возвращает (отправлено, кому предназначено)."""
    conn = get_conn()
    try:
        ann = conn.execute(
            """SELECT a.*, u.full_name AS author FROM announcements a
               JOIN users u ON u.id = a.author_id WHERE a.id = ?""", (ann_id,)
        ).fetchone()
        subs = conn.execute(
            "SELECT * FROM subscribers WHERE subject IN ('', ?)", (ann["subject"],)
        ).fetchall()
    finally:
        conn.close()
    if not ann or not subs:
        return 0, 0
    if not mailer.smtp_configured():
        return 0, len(subs)

    url = f"{str(request.base_url).rstrip('/')}/announcement/{ann_id}"
    lines = [
        f"Здравствуйте! В школе появился новый анонс.",
        "",
        f"{ann['title']}",
        f"Предмет: {ann['subject']} · {KINDS.get(ann['kind'], '')}",
    ]
    if ann["event_date"]:
        lines.append(f"Дата мероприятия: {ann['event_date']}")
    if ann["deadline"]:
        lines.append(f"Срок подачи заявок: {ann['deadline']}")
    lines += ["", f"Подробнее и файлы: {url}", "",
              f"Отписаться: {str(request.base_url).rstrip('/')}/unsubscribe/{{token}}"]
    body_template = "\n".join(lines)

    sent = 0
    for s in subs:
        body = body_template.replace("{token}", s["token"])
        if mailer.send_mail(s["email"], f"{SCHOOL_NAME} — {ann['title']}", body):
            sent += 1
    return sent, len(subs)


# ---------------------------------------------------------------- кабинет учителя

@app.get("/cabinet")
def cabinet(request: Request, user=Depends(require_teacher)):
    conn = get_conn()
    try:
        items = conn.execute(
            """SELECT a.*, (SELECT COUNT(*) FROM files f WHERE f.announcement_id = a.id) AS file_count
               FROM announcements a WHERE a.author_id = ?
               ORDER BY a.created_at DESC""",
            (user["id"],),
        ).fetchall()
    finally:
        conn.close()
    return render(request, "cabinet.html", items=items)


@app.get("/password")
def change_password_page(request: Request, user=Depends(require_user)):
    return render(request, "password.html", error=None)


@app.post("/password")
def change_password(request: Request, current: str = Form(...),
                    new: str = Form(...), new2: str = Form(...),
                    user=Depends(require_user)):
    if not security.verify_password(current, user["password_hash"]):
        return render(request, "password.html", error="Текущий пароль указан неверно")
    if len(new) < 6:
        return render(request, "password.html", error="Новый пароль — минимум 6 символов")
    if new != new2:
        return render(request, "password.html", error="Новые пароли не совпадают")
    conn = get_conn()
    try:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                     (security.hash_password(new), user["id"]))
        conn.commit()
    finally:
        conn.close()
    set_flash(request, "Пароль успешно изменён.")
    return RedirectResponse("/cabinet", status_code=303)


@app.get("/announcement/new")
def new_announcement(request: Request, user=Depends(require_teacher)):
    return render(request, "form.html", item=None, editing_files=[], error=None)


@app.post("/announcement/new")
async def create_announcement(
    request: Request,
    title: str = Form(...),
    subject: str = Form(...),
    kind: str = Form(...),
    description: str = Form(""),
    event_date: str = Form(""),
    deadline: str = Form(""),
    link: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user=Depends(require_teacher),
):
    title = title.strip()
    if not title:
        return render(request, "form.html", item=None, editing_files=[],
                      error="Укажите название")
    if kind not in KINDS:
        kind = "other"
    try:
        link = clean_link(link)
    except HTTPException as e:
        return render(request, "form.html", item=None, editing_files=[],
                      error=e.detail)
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO announcements
               (title, subject, kind, description, event_date, deadline, link, author_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, subject, kind, description.strip(),
             event_date or None, deadline or None, link, user["id"]),
        )
        conn.commit()
        ann_id = cur.lastrowid
    finally:
        conn.close()
    await save_uploads(files, ann_id)
    return RedirectResponse("/cabinet", status_code=303)


@app.get("/announcement/{ann_id}/edit")
def edit_announcement(request: Request, ann_id: int, user=Depends(require_teacher)):
    conn = get_conn()
    try:
        item = conn.execute("SELECT * FROM announcements WHERE id = ?",
                            (ann_id,)).fetchone()
        if not item or (item["author_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        files = conn.execute("SELECT * FROM files WHERE announcement_id = ?",
                             (ann_id,)).fetchall()
    finally:
        conn.close()
    return render(request, "form.html", item=item, editing_files=files, error=None)


@app.post("/announcement/{ann_id}/edit")
async def update_announcement(
    request: Request, ann_id: int,
    title: str = Form(...),
    subject: str = Form(...),
    kind: str = Form(...),
    description: str = Form(""),
    event_date: str = Form(""),
    deadline: str = Form(""),
    link: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user=Depends(require_teacher),
):
    conn = get_conn()
    try:
        item = conn.execute("SELECT * FROM announcements WHERE id = ?",
                            (ann_id,)).fetchone()
        if not item or (item["author_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        try:
            link = clean_link(link)
        except HTTPException as e:
            old_files = conn.execute(
                "SELECT * FROM files WHERE announcement_id = ?", (ann_id,)
            ).fetchall()
            return render(request, "form.html", item=item, editing_files=old_files,
                          error=e.detail)
        if kind not in KINDS:
            kind = "other"
        conn.execute(
            """UPDATE announcements SET title=?, subject=?, kind=?, description=?,
               event_date=?, deadline=?, link=?, status='pending' WHERE id=?""",
            (title.strip(), subject, kind, description.strip(),
             event_date or None, deadline or None, link, ann_id),
        )
        conn.commit()
        old_files = conn.execute(
            "SELECT * FROM files WHERE announcement_id = ?", (ann_id,)
        ).fetchall()
    finally:
        conn.close()
    await save_uploads(files, ann_id)
    return RedirectResponse("/cabinet", status_code=303)


@app.post("/announcement/{ann_id}/delete")
def delete_announcement(request: Request, ann_id: int, user=Depends(require_teacher)):
    conn = get_conn()
    try:
        item = conn.execute("SELECT * FROM announcements WHERE id = ?",
                            (ann_id,)).fetchone()
        if not item or (item["author_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status_code=404, detail="Объявление не найдено")
        files = conn.execute("SELECT stored_name FROM files WHERE announcement_id = ?",
                             (ann_id,)).fetchall()
        conn.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
        conn.commit()
    finally:
        conn.close()
    for f in files:
        path = db.UPLOAD_DIR / f["stored_name"]
        if path.exists():
            path.unlink()
    return RedirectResponse("/cabinet", status_code=303)


@app.get("/files/{file_id}/delete")
def delete_file(request: Request, file_id: int, user=Depends(require_teacher)):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT f.*, a.author_id FROM files f
               JOIN announcements a ON a.id = f.announcement_id WHERE f.id = ?""",
            (file_id,),
        ).fetchone()
        if not row or (row["author_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status_code=404, detail="Файл не найден")
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
        conn.commit()
    finally:
        conn.close()
    path = db.UPLOAD_DIR / row["stored_name"]
    if path.exists():
        path.unlink()
    return RedirectResponse(f"/announcement/{row['announcement_id']}/edit",
                            status_code=303)


# ---------------------------------------------------------------- модерация

@app.get("/admin")
def admin_queue(request: Request, user=Depends(require_admin)):
    conn = get_conn()
    try:
        pending = conn.execute(
            """SELECT a.*, u.full_name AS author FROM announcements a
               JOIN users u ON u.id = a.author_id
               WHERE a.status = 'pending' ORDER BY a.created_at"""
        ).fetchall()
        done = conn.execute(
            """SELECT a.*, u.full_name AS author FROM announcements a
               JOIN users u ON u.id = a.author_id
               WHERE a.status != 'pending' ORDER BY a.created_at DESC LIMIT 30"""
        ).fetchall()
    finally:
        conn.close()
    return render(request, "admin_queue.html", pending=pending, done=done)


@app.post("/admin/announcement/{ann_id}/{action}")
def moderate(request: Request, ann_id: int, action: str, user=Depends(require_admin)):
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=404)
    conn = get_conn()
    try:
        conn.execute("UPDATE announcements SET status = ? WHERE id = ?",
                     ("approved" if action == "approve" else "rejected", ann_id))
        conn.commit()
    finally:
        conn.close()
    if action == "approve":
        sent, total = notify_new_announcement(request, ann_id)
        if total and not mailer.smtp_configured():
            set_flash(request, f"Объявление опубликовано. Подписчиков ждут {total} писем, "
                               "но SMTP не настроен — письма не отправлены.", "warn")
        elif total:
            set_flash(request, f"Объявление опубликовано, писем отправлено: {sent} из {total}.")
        else:
            set_flash(request, "Объявление опубликовано.")
    else:
        set_flash(request, "Объявление отклонено.", "warn")
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/users")
def admin_users(request: Request, user=Depends(require_admin)):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY role, full_name"
        ).fetchall()
    finally:
        conn.close()
    return render(request, "admin_users.html", rows=rows)


@app.post("/admin/users/{user_id}")
def change_user(request: Request, user_id: int,
                role: str = Form(...), is_active: str = Form("0"),
                user=Depends(require_admin)):
    if role not in ("teacher", "admin"):
        role = "teacher"
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET role = ?, is_active = ? WHERE id = ?",
            (role, 1 if is_active == "1" else 0, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------- подписчики

@app.get("/admin/subscribers")
def admin_subscribers(request: Request, user=Depends(require_admin)):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM subscribers ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return render(request, "admin_subscribers.html", rows=rows,
                  smtp_ok=mailer.smtp_configured())


@app.post("/admin/subscribers/test")
def test_send(request: Request, email: str = Form(...), user=Depends(require_admin)):
    if mailer.send_mail(email.strip().lower(), "Тест рассылки",
                        f"Рассылка {SCHOOL_NAME} настроена и работает."):
        set_flash(request, f"Тестовое письмо отправлено на {email}.")
    else:
        set_flash(request, "Не удалось отправить письмо. Проверьте переменные "
                           "окружения SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.",
                  "error")
    return RedirectResponse("/admin/subscribers", status_code=303)


@app.post("/admin/subscribers/{sub_id}/delete")
def delete_subscriber(request: Request, sub_id: int, user=Depends(require_admin)):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM subscribers WHERE id = ?", (sub_id,))
        conn.commit()
    finally:
        conn.close()
    set_flash(request, "Подписчик удалён.", "warn")
    return RedirectResponse("/admin/subscribers", status_code=303)
