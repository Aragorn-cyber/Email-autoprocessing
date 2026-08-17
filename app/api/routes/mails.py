from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/mails", tags=["mails"])


@router.get("/{email_id}")
def get_mail(email_id: int, request: Request):
    return request.app.state.mail_service.get_detail(email_id)
