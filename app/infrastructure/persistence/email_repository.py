import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ResourceNotFoundError
from app.domain.entities import AnalyzedEmailReference, CompletedAnalysis, FetchedEmail
from app.infrastructure.models import (
    EmailAnalysisModel,
    EmailLinkSummaryModel,
    EmailModel,
    ProcessedUidModel,
    ScoreRuleDetailModel,
)


class EmailRepository:
    def __init__(self, session: Session):
        self.session = session

    def processed_analysis_reference(
        self,
        account_id: int,
        email: FetchedEmail,
    ) -> AnalyzedEmailReference | None:
        email_id = self.session.scalar(
            select(ProcessedUidModel.email_id).where(
                ProcessedUidModel.account_id == account_id,
                ProcessedUidModel.folder == email.folder,
                ProcessedUidModel.uid_validity == email.uid_validity,
                ProcessedUidModel.uid == email.uid,
            )
        )
        if email_id is None:
            return None
        analysis_id = self.session.scalar(
            select(EmailAnalysisModel.id)
            .where(EmailAnalysisModel.email_id == email_id)
            .order_by(EmailAnalysisModel.version.desc())
            .limit(1)
        )
        if analysis_id is None:
            raise ResourceNotFoundError(f"已处理邮件 {email_id} 缺少分析结果")
        return AnalyzedEmailReference(email_id=email_id, analysis_id=analysis_id)

    def store_raw(self, account_id: int, email: FetchedEmail) -> EmailModel:
        stored = self.session.scalar(
            select(EmailModel).where(
                EmailModel.account_id == account_id,
                EmailModel.folder == email.folder,
                EmailModel.uid_validity == email.uid_validity,
                EmailModel.uid == email.uid,
            )
        )
        values = {
            "message_id": email.message_id,
            "duplicate_group_key": self._duplicate_key(email),
            "subject": email.subject,
            "sender_name": email.sender_name,
            "sender_address": email.sender_address,
            "recipients_json": json.dumps(email.recipients, ensure_ascii=False),
            "sent_at": self._utc_datetime(email.sent_at),
            "received_at": self._utc_datetime(email.received_at),
            "body_text": email.body_text,
            "attachment_names_json": json.dumps(email.attachment_names, ensure_ascii=False),
            "attachment_count": len(email.attachment_names),
            "extracted_links_json": json.dumps(email.extracted_links, ensure_ascii=False),
        }
        if stored is None:
            stored = EmailModel(
                account_id=account_id,
                folder=email.folder,
                uid_validity=email.uid_validity,
                uid=email.uid,
                **values,
            )
            self.session.add(stored)
        else:
            for key, value in values.items():
                setattr(stored, key, value)
        self.session.flush()
        return stored

    def save_completed_analysis(
        self,
        stored_email: EmailModel,
        analysis: CompletedAnalysis,
    ) -> EmailAnalysisModel:
        current_version = self.session.scalar(
            select(func.max(EmailAnalysisModel.version)).where(
                EmailAnalysisModel.email_id == stored_email.id
            )
        )
        analysis_model = EmailAnalysisModel(
            email_id=stored_email.id,
            version=(current_version or 0) + 1,
            source_id=analysis.source_id,
            source_name=analysis.source_name,
            category_id=analysis.category_id,
            category_name=analysis.category_name,
            summary=analysis.summary,
            ai_reason=analysis.reason,
            rule_score=analysis.rule_score,
            semantic_score=analysis.semantic_score,
            total_score=analysis.total_score,
            importance=analysis.importance.value,
            discard_reason_summary=analysis.discard_reason_summary,
        )
        analysis_model.score_details = [
            ScoreRuleDetailModel(
                rule_code=hit.code,
                description=hit.description,
                score=hit.score,
            )
            for hit in analysis.rule_hits
        ]
        analysis_model.link_summaries = [
            EmailLinkSummaryModel(
                url=item.url,
                summary=item.summary,
                display_order=display_order,
            )
            for display_order, item in enumerate(analysis.link_summaries)
        ]
        self.session.add(analysis_model)
        self.session.flush()
        return analysis_model

    def mark_processed(self, account_id: int, stored_email: EmailModel) -> None:
        self.session.add(
            ProcessedUidModel(
                account_id=account_id,
                email_id=stored_email.id,
                folder=stored_email.folder,
                uid_validity=stored_email.uid_validity,
                uid=stored_email.uid,
            )
        )

    def get_detail(self, email_id: int) -> EmailModel:
        email = self.session.scalar(
            select(EmailModel)
            .options(
                selectinload(EmailModel.account),
                selectinload(EmailModel.analyses).selectinload(EmailAnalysisModel.score_details),
                selectinload(EmailModel.analyses).selectinload(EmailAnalysisModel.link_summaries),
            )
            .where(EmailModel.id == email_id)
        )
        if email is None:
            raise ResourceNotFoundError(f"邮件 {email_id} 不存在")
        return email

    def duplicate_members(self, duplicate_group_keys: set[str]) -> list[EmailModel]:
        if not duplicate_group_keys:
            return []
        return list(
            self.session.scalars(
                select(EmailModel)
                .options(selectinload(EmailModel.account))
                .where(EmailModel.duplicate_group_key.in_(duplicate_group_keys))
                .order_by(EmailModel.id)
            )
        )

    @staticmethod
    def _duplicate_key(email: FetchedEmail) -> str:
        if email.message_id:
            source = f"message-id:{email.message_id.strip().lower()}"
        else:
            source = "\n".join(
                (
                    email.subject.strip().lower(),
                    email.sender_address.strip().lower(),
                    email.sent_at.isoformat() if email.sent_at else "",
                    email.body_text[:1000].strip().lower(),
                )
            )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def latest_analysis(email: EmailModel) -> EmailAnalysisModel:
    if not email.analyses:
        raise ResourceNotFoundError(f"邮件 {email.id} 尚无分析结果")
    return email.analyses[-1]


def parse_json_list(value: str) -> list[str]:
    parsed = json.loads(value)
    return [str(item) for item in parsed]
