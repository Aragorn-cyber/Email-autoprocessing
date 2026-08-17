from dataclasses import dataclass, field
from datetime import datetime

from app.core.enums import ImportanceLevel


@dataclass(frozen=True, slots=True)
class MailboxConnection:
    account_id: int
    account_name: str
    email_address: str
    host: str
    port: int
    username: str
    password: str
    folder: str


@dataclass(frozen=True, slots=True)
class FetchedEmail:
    folder: str
    uid_validity: str
    uid: str
    message_id: str | None
    subject: str
    sender_name: str | None
    sender_address: str
    recipients: tuple[str, ...]
    sent_at: datetime | None
    received_at: datetime | None
    body_text: str
    attachment_names: tuple[str, ...]
    extracted_links: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleHit:
    code: str
    description: str
    score: int


@dataclass(frozen=True, slots=True)
class RuleScore:
    score: int
    hits: tuple[RuleHit, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AnalyzedLink:
    url: str
    summary: str


@dataclass(frozen=True, slots=True)
class SemanticAnalysis:
    source_suggestion: str | None
    category_name: str
    category_suggestion: str | None
    semantic_score: int
    reason: str
    summary: str
    discard_reason_summary: str | None
    link_summaries: tuple[AnalyzedLink, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CompletedAnalysis:
    source_id: int | None
    source_name: str
    category_id: int
    category_name: str
    rule_score: int
    semantic_score: int
    total_score: int
    importance: ImportanceLevel
    reason: str
    summary: str
    discard_reason_summary: str | None
    rule_hits: tuple[RuleHit, ...]
    link_summaries: tuple[AnalyzedLink, ...] = field(default_factory=tuple)
    source_suggestion: str | None = None
    category_suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyzedEmailReference:
    email_id: int
    analysis_id: int
