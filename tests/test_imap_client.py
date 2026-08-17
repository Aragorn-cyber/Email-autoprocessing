import imaplib
from datetime import datetime, timezone

import pytest

from app.core.exceptions import ExternalServiceError
from app.domain.entities import MailboxConnection
from app.infrastructure.imap.client import ImapEmailProvider


class FakeImapClient:
    def __init__(self, capabilities=(b"IMAP4rev1", b"ID"), select_result=("OK", [b"0"])):
        self.capabilities = capabilities
        self.select_result = select_result
        self.identity_calls = []
        self.login_calls = []
        self.select_calls = []

    def login(self, username, password):
        self.login_calls.append((username, password))
        return "OK", [b"LOGIN completed"]

    def capability(self):
        return "OK", [b" ".join(self.capabilities)]

    def _simple_command(self, command, value):
        self.identity_calls.append((command, value))
        return "OK", [b"ID completed"]

    def select(self, folder, readonly=True):
        self.select_calls.append((folder, readonly))
        return self.select_result

    def uid(self, command, *args):
        if command == "search":
            return "OK", [b""]
        raise AssertionError(f"unexpected uid command: {command}")

    def logout(self):
        return "BYE", [b"LOGOUT completed"]


def connection():
    return MailboxConnection(
        account_id=1,
        account_name="测试邮箱",
        email_address="user@example.com",
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="test-password",
        folder="INBOX",
    )


def test_imap_client_sends_identity_when_server_supports_id(monkeypatch):
    fake = FakeImapClient()
    monkeypatch.setattr(
        "app.infrastructure.imap.client.imaplib.IMAP4_SSL",
        lambda *args, **kwargs: fake,
    )
    monkeypatch.setattr("app.infrastructure.imap.client.imaplib.Commands", dict(imaplib.Commands))

    class Provider(ImapEmailProvider):
        def _uid_validity(self, client):
            return "100"

    Provider()._fetch_unread_sync(connection(), datetime.now(timezone.utc))

    assert fake.identity_calls == [
        ("ID", '("name" "email-ai-assistant" "version" "1.0")')
    ]
    assert fake.select_calls == [("INBOX", True)]


def test_imap_client_skips_identity_without_capability(monkeypatch):
    fake = FakeImapClient(capabilities=(b"IMAP4rev1",))
    monkeypatch.setattr(
        "app.infrastructure.imap.client.imaplib.IMAP4_SSL",
        lambda *args, **kwargs: fake,
    )
    monkeypatch.setattr("app.infrastructure.imap.client.imaplib.Commands", dict(imaplib.Commands))

    class Provider(ImapEmailProvider):
        def _uid_validity(self, client):
            return "100"

    Provider()._fetch_unread_sync(connection(), datetime.now(timezone.utc))

    assert fake.identity_calls == []


def test_imap_client_exposes_server_folder_error_without_credentials(monkeypatch):
    fake = FakeImapClient(
        select_result=("NO", [b"EXAMINE Unsafe Login. Please contact kefu@188.com for help"])
    )
    monkeypatch.setattr(
        "app.infrastructure.imap.client.imaplib.IMAP4_SSL",
        lambda *args, **kwargs: fake,
    )
    monkeypatch.setattr("app.infrastructure.imap.client.imaplib.Commands", dict(imaplib.Commands))

    with pytest.raises(ExternalServiceError, match="Unsafe Login"):
        ImapEmailProvider()._fetch_unread_sync(connection(), datetime.now(timezone.utc))
