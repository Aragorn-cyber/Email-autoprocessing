from fastapi import APIRouter, Query, Request, Response, status


router = APIRouter(prefix="/api/important-mails", tags=["important-mails"])


@router.get("")
def list_important_mails(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return request.app.state.important_mail_service.list_payload(page, page_size)


@router.post("/{email_id}", status_code=status.HTTP_201_CREATED)
def mark_mail_important(email_id: int, request: Request):
    record = request.app.state.important_mail_service.mark(email_id)
    return {"email_id": record.email_id, "marked_at": record.marked_at}


@router.delete("/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_mail_from_important_list(email_id: int, request: Request) -> Response:
    request.app.state.important_mail_service.remove(email_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
