"""Отправка писем по SMTP.

Настройки задаются переменными окружения:
  SMTP_HOST, SMTP_PORT (по умолчанию 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM
Если SMTP_HOST не задан — рассылка считается не настроенной.
"""
import os
import smtplib
from email.mime.text import MIMEText


def smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def send_mail(to: str, subject: str, body: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    if not host:
        return False
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM") or user or "noreply@localhost"

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass
            if user and password:
                server.login(user, password)
            server.sendmail(sender, [to], msg.as_string())
        return True
    except Exception:
        return False
