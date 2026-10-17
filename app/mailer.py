"""Sending email. "console" (development) writes the message to the log; "smtp" sends it
with the MAIL_* settings (any provider: Gmail Workspace, Zoho, Amazon SES, Mailgun...)."""
import smtplib
from email.message import EmailMessage

from flask import current_app


def send_email(to, subject, text):
    """Returns True if the message went out (or was logged in development)."""
    if not to:
        return False
    cfg = current_app.config
    if cfg["MAIL_PROVIDER"] == "console":
        current_app.logger.info("Email to %s: %s\n%s", to, subject, text)
        return True
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["MAIL_FROM"], to, subject
    msg.set_content(text)
    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as smtp:
            smtp.starttls()
            if cfg["MAIL_USERNAME"]:
                smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            smtp.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException):
        # A booking must never fail because email is down; the ticket page has everything.
        current_app.logger.exception("Email to %s not sent", to)
        return False
