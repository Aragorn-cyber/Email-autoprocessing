from datetime import datetime, timezone

import pytest

from app.core.config import ApplicationSettings
from app.domain.entities import FetchedEmail, SemanticAnalysis
from app.main import create_application


class FakeEmailProvider:
    def __init__(self, messages_by_account=None, failures=None):
        self.messages_by_account = messages_by_account or {}
        self.failures = failures or {}

    async def fetch_unread(self, connection, since):
        if connection.account_id in self.failures:
            raise RuntimeError(self.failures[connection.account_id])
        return self.messages_by_account.get(connection.account_id, [])


class FakeLanguageModel:
    def __init__(self, analyses=None, failure_subjects=None):
        self.analyses = analyses or {}
        self.failure_subjects = set(failure_subjects or [])
        self.calls = 0

    async def analyze_email(self, email, category_names):
        self.calls += 1
        if email.subject in self.failure_subjects:
            raise RuntimeError("模型失败")
        return self.analyses.get(
            email.subject,
            SemanticAnalysis(
                source_suggestion="测试来源",
                category_name="通知",
                category_suggestion=None,
                semantic_score=3,
                reason="含有明确的信息",
                summary=f"{email.subject} 的摘要",
                discard_reason_summary=None,
            ),
        )


def make_email(
    uid="1",
    subject="测试邮件",
    body="请确认本周五前提交。",
    message_id=None,
    sender="sender@example.com",
    sent_at=None,
    received_at=None,
    links=("https://example.com/action",),
):
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    return FetchedEmail(
        folder="INBOX",
        uid_validity="100",
        uid=str(uid),
        message_id=message_id or f"<{uid}@example.com>",
        subject=subject,
        sender_name="发件人",
        sender_address=sender,
        recipients=("user@example.com",),
        sent_at=sent_at or now,
        received_at=received_at or now,
        body_text=body,
        attachment_names=(),
        extracted_links=tuple(links),
    )


@pytest.fixture
def settings(tmp_path):
    return ApplicationSettings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        llm_api_key="test-key",
        whitelist_senders="trusted.example.com",
        blacklist_senders="ads.example.com",
        llm_retry_backoff_seconds=0,
    )


@pytest.fixture
def password_env(monkeypatch):
    monkeypatch.setenv("TEST_EMAIL_PASSWORD", "app-password")


def add_account(app, name="主邮箱", email_address="user@example.com", scan_window_days=7):
    with app.state.database.session_factory() as session:
        from app.infrastructure.persistence import MailboxAccountRepository

        account = MailboxAccountRepository(session).create(
            name=name,
            email_address=email_address,
            imap_host="imap.example.com",
            imap_port=993,
            username=email_address,
            password_env_name="TEST_EMAIL_PASSWORD",
            folder="INBOX",
            scan_window_days=scan_window_days,
        )
        session.commit()
        return account.id
