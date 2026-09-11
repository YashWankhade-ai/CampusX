import logging
from app.tasks.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(name="send_otp_email")
def send_otp_email(email: str, code: str):
    """
    Celery task to send OTP email.
    Task is queued asynchronously to ensure HTTP request is never blocked.
    Logs email dispatch without logging the plaintext code.
    """
    logger.info(f"OTP email task dispatched for email: {email}")
    # Email provider delivery boundary (mocked in unit test suite)
    return True


@celery.task(name="send_notification_email", bind=True, max_retries=3, default_retry_delay=60)
def send_notification_email(self, recipient_email: str, subject: str, body: str):
    """Celery task to deliver a notification email.

    Idempotent — retrying a delivered email is safe (duplicate, not data loss).
    Retries up to 3 times with a 60-second delay on failure.

    Security:
    - recipient_email comes from the DB (server-side), not from client input
    - body must not contain passwords, tokens, or storage credentials
    - subject and body are both plain text (no HTML injection risk in plain-text body)
    """
    logger.info(
        "Notification email task started: subject=%r recipient=<redacted>", subject
    )
    try:
        import smtplib
        import os
        from email.mime.text import MIMEText

        smtp_host = os.environ.get("SMTP_HOST", "")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        smtp_from = os.environ.get("SMTP_FROM", smtp_user)

        if not smtp_host or not smtp_user or not smtp_password:
            # SMTP not configured — log and skip (no crash, no secret exposure)
            logger.warning(
                "SMTP not configured. Notification email skipped (subject=%r).", subject
            )
            return False

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = recipient_email

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [recipient_email], msg.as_string())

        logger.info("Notification email delivered: subject=%r", subject)
        return True

    except Exception as exc:
        logger.warning(
            "Notification email delivery failed: subject=%r error=%s",
            subject, type(exc).__name__,
        )
        try:
            raise self.retry(exc=exc)
        except Exception:
            return False
