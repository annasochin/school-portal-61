@echo off
cd /d "%~dp0"
if not exist ".venv" (
    echo Создаю виртуальное окружение...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo.
echo Запуск: http://127.0.0.1:8000
echo Администратор: логин admin, пароль admin123 (смените!)
echo.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
