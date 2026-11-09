"""Middleware opcional: rate limit + logging."""
import os, sys

def _ssl():
    try:
        import logging, structlog
    except ImportError:
        return False
    if os.environ.get("STRUCTLOG_ENABLED","true").lower()!="true":
        return False
    try:
        structlog.configure(processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer()],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.PrintLoggerFactory())
        return True
    except Exception:
        return False

def _srl(app):
    if os.environ.get("RATE_LIMIT_ENABLED","true").lower()!="true":
        return None
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded
    except ImportError:
        return None
    try:
        lim = Limiter(key_func=get_remote_address,
            default_limits=[os.environ.get("RATE_LIMIT_DEFAULT","100/minute")])
        app.state.limiter = lim
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        return lim
    except Exception:
        return None

def apply_middleware(app):
    return {"limiter": _srl(app), "structured_logging": _ssl()}
