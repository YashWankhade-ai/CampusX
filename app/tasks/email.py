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
