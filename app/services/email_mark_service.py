from __future__ import annotations

from math import ceil

from app.infrastructure.persistence import latest_analysis
from app.infrastructure.persistence.email_mark_repository import EmailMarkRepository


class EmailMarkService:
    """本地标记名单的通用服务：已读、重要邮件等共用。"""

    repository_class: type[EmailMarkRepository]

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list(self, page: int, page_size: int):
        with self.session_factory() as session:
            return self.repository_class(session).list(page, page_size)

    def list_payload(self, page: int, page_size: int) -> dict:
        records, total_items = self.list(page, page_size)
        return {
            "data": [
                {
                    "email_id": record.email_id,
                    "marked_at": record.marked_at,
                    "subject": record.email.subject,
                    "sender_address": record.email.sender_address,
                    "account_name": record.email.account.name,
                    "summary": latest_analysis(record.email).summary,
                    "mail_url": f"/mail/{record.email_id}",
                }
                for record in records
            ],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": ceil(total_items / page_size) if total_items else 0,
            },
        }

    def mark(self, email_id: int):
        with self.session_factory() as session:
            record = self.repository_class(session).mark(email_id)
            session.commit()
            return record

    def remove(self, email_id: int) -> None:
        with self.session_factory() as session:
            self.repository_class(session).remove(email_id)
            session.commit()

    def mark_many(self, email_ids: list[int]) -> int:
        with self.session_factory() as session:
            count = self.repository_class(session).mark_many(email_ids)
            session.commit()
            return count

    def remove_all(self) -> int:
        with self.session_factory() as session:
            count = self.repository_class(session).remove_all()
            session.commit()
            return count
