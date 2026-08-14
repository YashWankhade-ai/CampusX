import logging
import sys

try:
    import structlog
except ImportError:
    structlog = None

def setup_logging(log_level: str = "INFO"):
    """
    Configures structured JSON logging using structlog in accordance with
    CampusX Architecture Specification Section 2.2 and Section 7.
    """
    logging_level = getattr(logging, log_level.upper(), logging.INFO)

    if structlog:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.dev.set_exc_info,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True
        )
    else:
        logging.basicConfig(
            level=logging_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout
        )
