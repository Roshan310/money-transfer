from fastapi import APIRouter

from app.accounts.router import router as accounts_router
from app.transfers.router import router as transfers_router

router = APIRouter(prefix="/api/v1")
router.include_router(accounts_router)
router.include_router(transfers_router)
