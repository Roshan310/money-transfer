from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.database import SessionDep
from app.errors import ErrorResponse
from app.transfers import service
from app.transfers.errors import TransferAccountNotFoundError, TransferConflictError
from app.transfers.schemas import TransferCreate, TransferRead

router = APIRouter(prefix="/transfers", tags=["transfers"])

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"\S")
]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Source or destination account not found",
        },
        409: {
            "model": ErrorResponse,
            "description": "Transfer or idempotency conflict",
        },
    },
    description=(
        "Requires an Idempotency-Key. Successful retries with equivalent payloads "
        "return the original transfer without moving money again. Failed requests "
        "do not reserve their keys. Amounts must be positive decimal strings."
    ),
)
def create_transfer(
    data: TransferCreate, session: SessionDep, idempotency_key: IdempotencyKey
) -> TransferRead:
    try:
        transfer = service.create_transfer(session, data, idempotency_key)
    except TransferAccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TransferConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TransferRead.model_validate(transfer)
