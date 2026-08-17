from fastapi import APIRouter, Query, Request, Response, status

from app.api.schemas import MarkReadBulkRequest


router = APIRouter(prefix="/api/read-mails", tags=["local-read-mails"])


@router.get("")
def list_read_mails(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return request.app.state.read_mail_service.list_payload(page, page_size)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
def mark_many_mails_read(payload: MarkReadBulkRequest, request: Request):
    marked = request.app.state.read_mail_service.mark_many(payload.email_ids)
    return {"marked": marked}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def remove_all_mails_from_read_list(request: Request) -> Response:
    request.app.state.read_mail_service.remove_all()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{email_id}", status_code=status.HTTP_201_CREATED)
def mark_mail_read(email_id: int, request: Request):
    record = request.app.state.read_mail_service.mark(email_id)
    return {"email_id": record.email_id, "marked_at": record.marked_at}


@router.delete("/{email_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_mail_from_read_list(email_id: int, request: Request) -> Response:
    request.app.state.read_mail_service.remove(email_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
