from flask import request, g
import logging

logger = logging.getLogger("audit")

def audit_middleware(response):
    """Log audit information for state-changing requests."""
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        user_id = getattr(g, "current_user", {}).get("sub", "anonymous")
        logger.info(
            f"Audit log: user={user_id} "
            f"method={request.method} "
            f"path={request.path} "
            f"status={response.status_code}"
        )
    return response
