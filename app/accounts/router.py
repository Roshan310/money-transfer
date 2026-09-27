from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.accounts import service
from app.accounts.schemas import AccountCreate, AccountRead, AccountTransactionPage
from app.database import SessionDep
from app.errors import ErrorResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])

# I implemented this only for the ease of finding account uuids for transfer tests.
@router.get("", response_model=list[AccountRead])
def get_all_accounts(session: SessionDep) -> list[AccountRead]:
    accounts = service.get_all_accounts(session)
    return [AccountRead.model_validate(account) for account in accounts]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, session: SessionDep) -> AccountRead:
    account = service.create_account(session, data)
    return AccountRead.model_validate(account)


@router.get(
    "/{account_id}",
    responses={404: {"model": ErrorResponse, "description": "Account not found"}},
)
def get_account(account_id: UUID, session: SessionDep) -> AccountRead:
    try:
        account = service.get_account(session, account_id)
    except service.AccountNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        ) from exc
    return AccountRead.model_validate(account)


@router.get(
    "/{account_id}/transactions",
    summary="Get incoming and outgoing transfers for an account",
    description="Newest first by creation time and ID. Opening balances are excluded.",
    responses={404: {"model": ErrorResponse, "description": "Account not found"}},
)
def get_transaction_history(
    account_id: UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    offset: Annotated[int, Query(ge=0, description="Number of entries to skip")] = 0,
) -> AccountTransactionPage:
    try:
        return service.get_transaction_history(
            session, account_id, limit=limit, offset=offset
        )
    except service.AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Account not found") from exc
