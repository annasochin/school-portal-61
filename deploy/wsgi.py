# Для хостингов, где сайт подключается как WSGI-приложение (например, PythonAnywhere).
# Точка входа — переменная `app` из этого файла.
from app.main import app  # noqa: F401
