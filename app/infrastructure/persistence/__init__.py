from app.infrastructure.persistence.account_repository import MailboxAccountRepository
from app.infrastructure.persistence.classification_repository import ClassificationRepository
from app.infrastructure.persistence.email_repository import (
    EmailRepository,
    latest_analysis,
    parse_json_list,
)
from app.infrastructure.persistence.report_repository import ReportRepository
from app.infrastructure.persistence.read_mail_repository import LocalReadMailRepository
from app.infrastructure.persistence.important_mail_repository import ImportantMailRepository
from app.infrastructure.persistence.scan_repository import ScanRepository

__all__ = [
    "ClassificationRepository",
    "EmailRepository",
    "MailboxAccountRepository",
    "ImportantMailRepository",
    "LocalReadMailRepository",
    "ReportRepository",
    "ScanRepository",
    "latest_analysis",
    "parse_json_list",
]
