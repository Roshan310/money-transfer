from fastapi import FastAPI

from app.accounts.router import router as accounts_router
from app.transfers.router import router as transfers_router


def create_app() -> FastAPI:
    app = FastAPI(title="Money Transfer System", version="0.1.0")
    app.include_router(accounts_router)
    app.include_router(transfers_router)
    return app


app = create_app()


@app.get("/")
def status():
    return {
        "message": "Welcome to the Money Transfer System! Everthing is working fine."
    }
