from datetime import datetime, timezone
from email.message import EmailMessage

from app.infrastructure.imap.client import ImapEmailProvider
from app.core.link_policy import normalize_safe_link, report_links


def test_imap_parser_converts_html_and_records_attachment_metadata():
    message = EmailMessage()
    message["Subject"] = "HTML 邮件"
    message["From"] = "Sender <sender@example.com>"
    message["To"] = "user@example.com"
    message["Message-ID"] = "<html@example.com>"
    message.set_content("纯文本 https://example.com/plain")
    message.add_alternative(
        '<html><body><p>正文内容</p><a href="https://example.com/html">入口</a></body></html>',
        subtype="html",
    )
    message.add_attachment(b"file", maintype="application", subtype="pdf", filename="说明.pdf")

    parsed = ImapEmailProvider._parse_message(message.as_bytes(), "INBOX", "100", "1")

    assert "纯文本" in parsed.body_text
    assert parsed.attachment_names == ("说明.pdf",)
    assert set(parsed.extracted_links) == {
        "https://example.com/plain",
        "https://example.com/html",
    }


def test_imap_parser_uses_internaldate_as_received_time_and_filters_unsafe_links():
    message = EmailMessage()
    message["Subject"] = "转发邮件"
    message["From"] = "Sender <sender@example.com>"
    message["To"] = "user@example.com"
    message["Date"] = "Tue, 1 Jan 2019 08:00:00 +0800"
    message.set_content("原始内容")
    message.add_alternative(
        '<a href="javascript:alert(1)">危险</a><a href="https://safe.example.com/path">安全</a>',
        subtype="html",
    )
    received_at = datetime(2026, 8, 13, 15, 30, tzinfo=timezone.utc)

    parsed = ImapEmailProvider._parse_message(
        message.as_bytes(),
        "INBOX",
        "100",
        "1",
        received_at=received_at,
    )

    assert parsed.received_at == received_at
    assert parsed.sent_at.year == 2019
    assert parsed.extracted_links == ("https://safe.example.com/path",)


def test_link_policy_rejects_malformed_ports_instead_of_raising():
    assert normalize_safe_link("https://example.com:invalid/path") is None


def test_report_links_drop_tracking_and_signature_assets():
    assert report_links(
        [
            "https://example.com/register",
            "https://t.edm.example.com/activities_web/track/click?id=1",
            "https://t.edm.example.com/activities_web/sample/click?id=2",
            "https://example.com/emaildisclaimer/icon.jpg",
            "https://example.com/banner.png",
        ]
    ) == ("https://example.com/register",)
