import logging
import uuid
import re
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Regex pattern for valid request IDs (UUID or alphanumeric with hyphens)
REQUEST_ID_PATTERN = re.compile(r'^[a-zA-Z0-9\-]{8,128}$')


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to inject X-Request-ID header for request tracing.
    
    If client provides X-Request-ID, it's used. Otherwise, a new UUID is generated.
    The request ID is added to response headers and log context.
    """
    
    def __init__(self, app: ASGIApp): super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get client-provided request ID, validate to prevent injection
        client_request_id = request.headers.get("X-Request-ID")
        
        if client_request_id:
            # Validate format to prevent log injection and other attacks
            if REQUEST_ID_PATTERN.match(client_request_id):
                request_id: str = client_request_id
            else:
                # Invalid format, generate new ID and log warning
                request_id = str(uuid.uuid4())
                logger.warning(
                    f"Invalid X-Request-ID format rejected: {client_request_id[:50]}",
                    extra={"generated_id": request_id}
                )
        else:
            request_id = str(uuid.uuid4())
        
        request.state.request_id = request_id
        extra = {"request_id": request_id, "path": request.url.path}
        logger.info(f"Request started", extra=extra)
        
        response = await call_next(request)
        
        response.headers["X-Request-ID"] = request_id
        
        logger.info(
            f"Request completed",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "status_code": response.status_code,
            }
        )
        
        return response


def get_request_id(request: Request) -> str: return getattr(request.state, "request_id", "unknown")
