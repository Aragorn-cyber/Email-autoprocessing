from fastapi import APIRouter, Request, status

from app.api.schemas import AccountCreateRequest, AccountResponse, AccountUpdateRequest


router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(request: Request):
    return request.app.state.account_service.list_accounts()


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreateRequest, request: Request):
    return request.app.state.account_service.create_account(payload.model_dump())


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: int,
    payload: AccountUpdateRequest,
    request: Request,
):
    return request.app.state.account_service.update_account(
        account_id,
        payload.model_dump(exclude_none=True),
    )
