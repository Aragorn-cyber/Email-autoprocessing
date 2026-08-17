from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import DatabaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MailboxAccountModel(DatabaseModel):
    __tablename__ = "mailbox_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email_address: Mapped[str] = mapped_column(String(320), unique=True)
    imap_host: Mapped[str] = mapped_column(String(255))
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    username: Mapped[str] = mapped_column(String(320))
    password_env_name: Mapped[str] = mapped_column(String(120))
    folder: Mapped[str] = mapped_column(String(255), default="INBOX")
    scan_window_days: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class EmailModel(DatabaseModel):
    __tablename__ = "email"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "folder",
            "uid_validity",
            "uid",
            name="uq_email_imap_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("mailbox_account.id"), index=True)
    folder: Mapped[str] = mapped_column(String(255))
    uid_validity: Mapped[str] = mapped_column(String(64))
    uid: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str | None] = mapped_column(String(998), index=True)
    duplicate_group_key: Mapped[str] = mapped_column(String(128), index=True)
    subject: Mapped[str] = mapped_column(Text)
    sender_name: Mapped[str | None] = mapped_column(String(320))
    sender_address: Mapped[str] = mapped_column(String(320), index=True)
    recipients_json: Mapped[str] = mapped_column(Text, default="[]")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    body_text: Mapped[str] = mapped_column(Text)
    attachment_names_json: Mapped[str] = mapped_column(Text, default="[]")
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    extracted_links_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    account: Mapped[MailboxAccountModel] = relationship()
    analyses: Mapped[list["EmailAnalysisModel"]] = relationship(
        back_populates="email",
        order_by="EmailAnalysisModel.version",
    )


class ProcessedUidModel(DatabaseModel):
    __tablename__ = "processed_uid"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "folder",
            "uid_validity",
            "uid",
            name="uq_processed_uid_imap_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("mailbox_account.id"), index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email.id"), unique=True)
    folder: Mapped[str] = mapped_column(String(255))
    uid_validity: Mapped[str] = mapped_column(String(64))
    uid: Mapped[str] = mapped_column(String(64))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LocalReadMailModel(DatabaseModel):
    __tablename__ = "local_read_mail"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email.id"), unique=True, index=True)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    email: Mapped[EmailModel] = relationship()


class ImportantMailModel(DatabaseModel):
    __tablename__ = "important_mail"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email.id"), unique=True, index=True)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    email: Mapped[EmailModel] = relationship()


class SourceModel(DatabaseModel):
    __tablename__ = "source"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    rules: Mapped[list["SourceRuleModel"]] = relationship(back_populates="source")


class SourceRuleModel(DatabaseModel):
    __tablename__ = "source_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), index=True)
    match_type: Mapped[str] = mapped_column(String(20))
    pattern: Mapped[str] = mapped_column(String(320), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    source: Mapped[SourceModel] = relationship(back_populates="rules")


class CategoryModel(DatabaseModel):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EmailAnalysisModel(DatabaseModel):
    __tablename__ = "email_analysis"
    __table_args__ = (UniqueConstraint("email_id", "version", name="uq_email_analysis_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"))
    source_name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    category_name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    ai_reason: Mapped[str] = mapped_column(Text)
    rule_score: Mapped[int] = mapped_column(Integer)
    semantic_score: Mapped[int] = mapped_column(Integer)
    total_score: Mapped[int] = mapped_column(Integer)
    importance: Mapped[str] = mapped_column(String(20), index=True)
    discard_reason_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    email: Mapped[EmailModel] = relationship(back_populates="analyses")
    source: Mapped[SourceModel | None] = relationship()
    category: Mapped[CategoryModel] = relationship()
    score_details: Mapped[list["ScoreRuleDetailModel"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    link_summaries: Mapped[list["EmailLinkSummaryModel"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="EmailLinkSummaryModel.display_order",
    )


class ScoreRuleDetailModel(DatabaseModel):
    __tablename__ = "score_rule_detail"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("email_analysis.id"), index=True)
    rule_code: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)

    analysis: Mapped[EmailAnalysisModel] = relationship(back_populates="score_details")


class EmailLinkSummaryModel(DatabaseModel):
    __tablename__ = "email_link_summary"
    __table_args__ = (
        UniqueConstraint("analysis_id", "url", name="uq_analysis_link_summary_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("email_analysis.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(String(240))
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    analysis: Mapped[EmailAnalysisModel] = relationship(back_populates="link_summaries")


class ScanRecordModel(DatabaseModel):
    __tablename__ = "scan_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), index=True)
    account_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    processed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    errors_json: Mapped[str] = mapped_column(Text, default="[]")


class ReportModel(DatabaseModel):
    __tablename__ = "report"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scan_record.id"), unique=True)
    earliest_email_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_email_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overview: Mapped[str] = mapped_column(Text)
    snapshot_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    scan: Mapped[ScanRecordModel] = relationship()


class ClassificationSuggestionModel(DatabaseModel):
    __tablename__ = "classification_suggestion"

    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_type: Mapped[str] = mapped_column(String(20), index=True)
    proposed_name: Mapped[str] = mapped_column(String(120))
    proposed_pattern: Mapped[str | None] = mapped_column(String(320))
    email_id: Mapped[int | None] = mapped_column(ForeignKey("email.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
