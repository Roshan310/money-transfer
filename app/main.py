from fastapi import FastAPI

from app.api import router as api_router
from app.errors import ErrorResponse, unexpected_error_handler


def create_app() -> FastAPI:
    app = FastAPI(
        title="Money Transfer System",
        version="0.1.0",
        description="Account management and atomic, idempotent money transfers.",
        responses={500: {"model": ErrorResponse, "description": "Unexpected error"}},
    )
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(api_router)
    return app


app = create_app()


@app.get("/")
def status():
    return {
        "message": "Welcome to the Money Transfer System! Everything is working fine."
    }
