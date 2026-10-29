"""Gửi email (xác minh, đặt lại mật khẩu, cảnh báo admin).

SMTP_HOST rỗng ⇒ chế độ "console": in thư ra log thay vì gửi (dùng khi chạy thử / test). Mọi thư cũng
được giữ trong OUTBOX (bộ nhớ, tối đa 50 thư) để test đọc được.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from collections import deque
from email.message import EmailMessage

from .config import Settings

log = logging.getLogger("cloud.mail")
OUTBOX: deque[dict] = deque(maxlen=50)


def send(settings: Settings, to: str, subject: str, body: str) -> bool:
    """→ True nếu gửi được. Lỗi gửi thư không được làm hỏng request (chỉ log)."""
    OUTBOX.append({"to": to, "subject": subject, "body": body})
    if settings.mail_mode == "console":
        log.warning("[mail:console] To: %s | %s\n%s", to, subject, body)
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_pass)
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.error("Gửi email thất bại (%s): %s", subject, exc)
        return False


def alert_admin(settings: Settings, subject: str, body: str) -> None:
    if settings.admin_email:
        send(settings, settings.admin_email, "[Match Performance] " + subject, body)
    else:
        log.warning("[alert] %s — %s", subject, body)
