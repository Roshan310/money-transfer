from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.accounts import service
from app.accounts.schemas import AccountCreate, AccountRead
from app.database import SessionDep

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, session: SessionDep) -> AccountRead:
    account = service.create_account(session, data)
    return AccountRead.model_validate(account)


@router.get("/{account_id}", responses={404: {"description": "Account not found"}})
def get_account(account_id: UUID, session: SessionDep) -> AccountRead:
    try:
        account = service.get_account(session, account_id)
    except service.AccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        ) from exc
    return AccountRead.model_validate(account)
