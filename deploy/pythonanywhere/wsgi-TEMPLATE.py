# Файл настроек сайта для PythonAnywhere (WSGI).
# Откройте его на странице Web → "your WSGI configuration file",
# удалите всё содержимое и вставьте этот код.
# Перед сохранением замените USERNAME на свой логин PythonAnywhere.

import os
import sys

# Папка, куда распакован сайт (путь должен совпадать с реальным!)
PROJECT_PATH = "/home/USERNAME/school-portal"
if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)

# Где хранить базу данных и загруженные файлы
os.environ.setdefault("DATA_DIR", PROJECT_PATH)

from a2wsgi import ASGIMiddleware

from app.main import app as asgi_application

# FastAPI — это ASGI-приложение, PythonAnywhere запускает WSGI,
# поэтому оборачиваем совместимым адаптером
application = ASGIMiddleware(asgi_application)
