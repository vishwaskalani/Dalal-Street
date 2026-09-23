"""
mailer.py — send a plain-text email with a file attached, over SMTP/SSL.

Credentials come from the environment (or .env), never from code:
    SMTP_USER       sender address, e.g. you@gmail.com
    SMTP_PASSWORD   for Gmail, a 16-character App Password (not your login password)
    SMTP_HOST       optional, default smtp.gmail.com
    SMTP_PORT       optional, default 465

Usage:
    from screener import mailer
    mailer.send(["a@x.com"], "Subject", "Body text", attachment="delta.csv")
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv


def send(
    recipients: list[str],
    subject: str,
    body: str,
    attachment: str | None = None,
) -> None:
    load_dotenv()
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    if not user or not password:
        raise RuntimeError("SMTP_USER and SMTP_PASSWORD must be set to send mail.")

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    if attachment:
        with open(attachment, "rb") as fh:
            msg.add_attachment(
                fh.read(), maintype="text", subtype="csv",
                filename=os.path.basename(attachment),
            )

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as server:
        server.login(user, password)
        server.send_message(msg)
