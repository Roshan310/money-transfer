import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    detail: str


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
