import logging
import time
from flask import request

logger = logging.getLogger("request_logger")

def request_logger_before():
    """Log start of request."""
    request.start_time = time.time()
    
def request_logger_after(response):
    """Log end of request with duration."""
    if hasattr(request, "start_time"):
        duration = time.time() - request.start_time
        logger.info(
            f"Request: method={request.method} "
            f"path={request.path} "
            f"status={response.status_code} "
            f"duration={duration:.3f}s "
            f"ip={request.remote_addr}"
        )
    return response
