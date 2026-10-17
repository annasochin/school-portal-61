# Презентация портала — исходники

- **presentation.html** — HTML-версия презентации (7 слайдов, тот же дизайн).
  Открывается в браузере: Ctrl+P → «Сохранить как PDF», размер страницы
  1280×720 px, поля «нет».
- **build_pptx.py** — сборка PowerPoint-версии:

  ```bat
  ..\.venv\Scripts\python.exe presentation\build_pptx.py
  ```

  Выход: `<корень проекта>\Презентация-портал-61.pptx` (нужен `pip install python-pptx qrcode`).

- **PDF одной командой** (без PowerPoint):

  ```bat
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --no-pdf-header-footer --print-to-pdf=deck.pdf presentation\presentation.html
  ```

- **home.png / calendar.png / print.png** — скриншоты сайта для слайдов
  (снимаются с локального сервера, где есть демо-данные).
- **logo.png** — логотип школы; **qr.png** — QR-код на живой сайт.

После обновления сайта переснимите скриншоты и пересоберите обе версии.
