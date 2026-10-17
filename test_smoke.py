"""Быстрый смоук-тест основных сценариев (запускать при включённом сервере)."""
import httpx

BASE = "http://127.0.0.1:8000"
results = []


def check(name, cond, extra=""):
    results.append(("OK " if cond else "FAIL", name, extra))


c = httpx.Client(base_url=BASE, follow_redirects=False, timeout=15)

# 1. Главная и страницы без входа
r = c.get("/")
check("Главная открывается", r.status_code == 200 and "Олимпиады" in r.text)
check("/login открывается", c.get("/login").status_code == 200)
check("/register открывается", c.get("/register").status_code == 200)
check("Кабинет без входа -> редирект",
      c.get("/cabinet").status_code == 303)

# 2. Регистрация учителя
t = httpx.Client(base_url=BASE, follow_redirects=False, timeout=15)
r = t.post("/register", data={
    "login_name": "ivanova", "password": "secret1", "password2": "secret1",
    "full_name": "Иванова Мария Петровна", "subject": "Математика",
})
check("Регистрация учителя", r.status_code == 303, str(r.status_code))

# 3. Создание анонса с файлом
r = t.post("/announcement/new", data={
    "title": "Олимпиада «Кенгуру» 2026", "subject": "Математика",
    "kind": "olympiad",
    "description": "Школьный этап для 5–11 классов. Участие бесплатное.",
    "event_date": "2027-03-19", "deadline": "2027-03-01",
    "link": "https://example.com/kenguru",
}, files=[("files", ("polozhenie.pdf", b"%PDF-1.4 test", "application/pdf"))])
check("Создание анонса с файлом", r.status_code == 303, str(r.status_code))

r = t.get("/cabinet")
check("Анонс в кабинете со статусом «На модерации»",
      "На модерации" in r.text and "Кенгуру" in r.text)

# 4. Анонс не виден на главной до модерации
check("Неопубликованный анонс скрыт", "Кенгуру" not in c.get("/").text)

# 5. Вход администратором и модерация
a = httpx.Client(base_url=BASE, follow_redirects=False, timeout=15)
r = a.post("/login", data={"login_name": "admin", "password": "admin123"})
check("Вход администратора", r.status_code == 303)
r = a.get("/admin")
check("Страница модерации", r.status_code == 200 and "Кенгуру" in r.text)
import re
m = re.search(r"/admin/announcement/(\d+)/approve", r.text)
check("Анонс в очереди модерации", bool(m))
ann_id = m.group(1) if m else "0"
check("Одобрение анонса",
      a.post(f"/admin/announcement/{ann_id}/approve").status_code == 303)

# 6. Публикация видна всем, файл скачивается
check("Анонс виден на главной", "Кенгуру" in c.get("/").text)
r = c.get(f"/announcement/{ann_id}")
check("Страница анонса открывается", r.status_code == 200 and "Кенгуру" in r.text)
m2 = re.search(r"/files/(\d+)", r.text)
check("Файл в анонсе", bool(m2))
if m2:
    rf = c.get(f"/files/{m2.group(1)}")
    check("Файл скачивается", rf.status_code == 200 and rf.content.startswith(b"%PDF"))

# 7. Фильтры
check("Фильтр по предмету", "Кенгуру" in c.get("/?subject=Математика").text)
check("Фильтр по типу скрывает", "Кенгуру" not in c.get("/?kind=contest").text)
check("Поиск находит", "Кенгуру" in c.get("/?q=Кенгуру").text)

# 8. Название школы и календарь
main_html = c.get("/").text
check("Название школы в шапке", "МБОУ СОШ № 61 им. П. Е. Ладана" in main_html)
r = c.get("/calendar")
check("Календарь открывается", r.status_code == 200 and "Календарь" in r.text)
check("Событие в календаре (март 2027)", "Кенгуру" in c.get("/calendar?month=2027-03").text)
check("Ближайшие события", "Ближайшие события" in r.text)

# 9. Подписка
r = c.get("/subscribe")
check("Страница подписки", r.status_code == 200 and "Подписка" in r.text)
r = c.post("/subscribe", data={"email": "uchenik@mail.ru", "student_class": "7",
                               "subject": "Математика"})
check("Подписка оформлена", r.status_code == 303)
r = c.post("/subscribe", data={"email": "не-почта", "student_class": "7", "subject": ""})
check("Неверная почта отклоняется", "Проверьте адрес" in r.text)

# 10. Письма при публикации (SMTP не настроен — просто считаем)
r = a.get("/admin")
check("Предупреждение о письмах при одобрении",
      "Объявление опубликовано" in r.text)
r = a.get("/admin/subscribers")
check("Подписчик в админке", "uchenik@mail.ru" in r.text)

# 11. Смена пароля
r = a.post("/password", data={"current": "admin123", "new": "NovyjParol1",
                              "new2": "NovyjParol1"})
check("Смена пароля", r.status_code == 303, str(r.status_code))
b = httpx.Client(base_url=BASE, follow_redirects=False, timeout=15)
r = b.post("/login", data={"login_name": "admin", "password": "admin123"})
check("Старый пароль отклонён", r.status_code == 200)
r = b.post("/login", data={"login_name": "admin", "password": "NovyjParol1"})
check("Новый пароль работает", r.status_code == 303)
r = b.post("/password", data={"current": "never", "new": "abcdef",
                              "new2": "abcdef"})
check("Неверный текущий пароль отклонён", "указан неверно" in r.text)

# 12. О школе, RSS, печатная карточка
main_html = c.get("/").text
r = c.get("/about")
check("Страница «О школе»", r.status_code == 200 and "Персиановский" in r.text)
check("Пункт «О школе» в меню", 'href="/about"' in main_html)
check("RSS объявлен в шапке", 'type="application/rss+xml"' in main_html)
r = c.get("/rss.xml")
check("RSS: тип и формат",
      r.status_code == 200
      and "rss" in r.headers.get("content-type", "")
      and '<rss version="2.0">' in r.text)
check("RSS: анонс попал в ленту", "Кенгуру" in r.text)
check("RSS: описание с датами", "Дата мероприятия" in r.text)
r = c.get(f"/announcement/{ann_id}/print")
check("Печатная карточка открывается",
      r.status_code == 200 and "Кенгуру" in r.text and "window.print()" in r.text)
r = c.get(f"/announcement/{ann_id}")
check("Кнопка печати в объявлении",
      f'/announcement/{ann_id}/print' in r.text)
r = c.get("/calendar?month=2027-03")
check("Кнопка печати в календаре", "/print" in r.text)

for status, name, extra in results:
    print(f"{status} {name} {extra}")
print(f"\nИтого: {sum(1 for s, *_ in results if s == 'OK ')} OK, "
      f"{sum(1 for s, *_ in results if s == 'FAIL')} FAIL")
