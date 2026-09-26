from fastapi import FastAPI

from app.accounts.router import router as accounts_router


def create_app() -> FastAPI:
    app = FastAPI(title="Money Transfer System", version="0.1.0")
    app.include_router(accounts_router)
    return app


app = create_app()
