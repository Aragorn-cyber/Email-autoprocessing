import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.infrastructure.persistence import (
    EmailRepository,
    ImportantMailRepository,
    LocalReadMailRepository,
    MailboxAccountRepository,
    ClassificationRepository,
    ReportRepository,
    latest_analysis,
)
from app.services.report_service import ReportService


router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def format_datetime(value: datetime | str | None, fallback: str = "时间未知") -> str:
    if value is None:
        return fallback
    parsed = value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return parsed.strftime("%Y年%m月%d日 %H:%M")


templates.env.filters["datetime_zh"] = format_datetime


@router.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    accounts = MailboxAccountRepository(session).list()
    report = ReportRepository(session).latest()
    snapshot = ReportService.snapshot(report) if report else None
    recent_reports = ReportRepository(session).list(limit=4)
    read_count = len(LocalReadMailRepository(session).marked_email_ids())
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "accounts": accounts,
            "report": report,
            "snapshot": snapshot,
            "recent_reports": recent_reports,
            "read_count": read_count,
            "default_window_days": request.app.state.settings.default_scan_window_days,
        },
    )


@router.get("/reports/{report_id:int}", response_class=HTMLResponse)
def report_page(report_id: int, request: Request, session: Session = Depends(get_session)):
    report = ReportRepository(session).get(report_id)
    snapshot = ReportService.snapshot(report)
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "report": report,
            "snapshot": snapshot,
            "marked_read_ids": LocalReadMailRepository(session).marked_email_ids(),
            "marked_important_ids": ImportantMailRepository(session).marked_email_ids(),
        },
    )


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request, session: Session = Depends(get_session)):
    reports = ReportRepository(session).list(limit=50)
    report_items = [
        {"report": report, "snapshot": ReportService.snapshot(report)}
        for report in reports
    ]
    return templates.TemplateResponse(
        request,
        "reports.html",
        {"report_items": report_items},
    )


@router.get("/read-mails", response_class=HTMLResponse)
def read_mails_page(
    request: Request,
    page: int = 1,
    session: Session = Depends(get_session),
):
    page = max(page, 1)
    records, total_items = LocalReadMailRepository(session).list(page, 20)
    classifications = ClassificationRepository(session)
    items = [
        {
            "record": record,
            "email": record.email,
            "analysis": latest_analysis(record.email),
            "source_name": classifications.display_source_name(
                record.email.sender_address
            ),
        }
        for record in records
    ]
    return templates.TemplateResponse(
        request,
        "read_mails.html",
        {
            "items": items,
            "page": page,
            "total_items": total_items,
            "has_previous": page > 1,
            "has_next": page * 20 < total_items,
        },
    )


@router.get("/important-mails", response_class=HTMLResponse)
def important_mails_page(
    request: Request,
    page: int = 1,
    session: Session = Depends(get_session),
):
    page = max(page, 1)
    records, total_items = ImportantMailRepository(session).list(page, 20)
    classifications = ClassificationRepository(session)
    items = [
        {
            "record": record,
            "email": record.email,
            "analysis": latest_analysis(record.email),
            "source_name": classifications.display_source_name(
                record.email.sender_address
            ),
        }
        for record in records
    ]
    return templates.TemplateResponse(
        request,
        "important_mails.html",
        {
            "items": items,
            "page": page,
            "total_items": total_items,
            "has_previous": page > 1,
            "has_next": page * 20 < total_items,
        },
    )


@router.get("/mail/{email_id}", response_class=HTMLResponse)
def mail_page(email_id: int, request: Request, session: Session = Depends(get_session)):
    email = EmailRepository(session).get_detail(email_id)
    analysis = latest_analysis(email)
    return templates.TemplateResponse(
        request,
        "mail.html",
        {
            "email": email,
            "analysis": analysis,
            "source_name": ClassificationRepository(session).display_source_name(
                email.sender_address
            ),
            "recipients": json.loads(email.recipients_json),
            "attachments": json.loads(email.attachment_names_json),
            "links": json.loads(email.extracted_links_json),
            "link_summaries": analysis.link_summaries,
            "is_marked_read": LocalReadMailRepository(session).is_marked(email_id),
        },
    )
