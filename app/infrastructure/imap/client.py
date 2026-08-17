import asyncio
import email
import imaplib
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime

from bs4 import BeautifulSoup

from app.core.exceptions import ExternalServiceError
from app.core.link_policy import report_links
from app.domain.entities import FetchedEmail, MailboxConnection
from app.domain.interfaces import EmailProvider


class ImapEmailProvider(EmailProvider):
    async def fetch_unread(
        self,
        connection: MailboxConnection,
        since: datetime,
    ) -> list[FetchedEmail]:
        return await asyncio.to_thread(self._fetch_unread_sync, connection, since)

    def _fetch_unread_sync(
        self,
        connection: MailboxConnection,
        since: datetime,
    ) -> list[FetchedEmail]:
        client: imaplib.IMAP4_SSL | None = None
        try:
            client = imaplib.IMAP4_SSL(connection.host, connection.port, timeout=30)
            client.login(connection.username, connection.password)
            self._send_client_identity(client)
            status, _ = client.select(connection.folder, readonly=True)
            if status != "OK":
                detail = self._response_detail(_)
                message = f"无法打开邮箱文件夹 {connection.folder}"
                if detail:
                    message = f"{message}：{detail}"
                raise ExternalServiceError(message)
            since_date = since.astimezone(timezone.utc).strftime("%d-%b-%Y")
            status, data = client.uid("search", None, "UNSEEN", "SINCE", since_date)
            if status != "OK":
                raise ExternalServiceError("IMAP 搜索未读邮件失败")
            uids = data[0].split() if data and data[0] else []
            uid_validity = self._uid_validity(client)
            messages: list[FetchedEmail] = []
            for uid in uids:
                status, fetched = client.uid("fetch", uid, "(RFC822 INTERNALDATE)")
                if status != "OK":
                    continue
                raw = next((part[1] for part in fetched if isinstance(part, tuple)), None)
                if not raw:
                    continue
                messages.append(
                    self._parse_message(
                        raw,
                        connection.folder,
                        uid_validity,
                        uid.decode(),
                        received_at=self._internal_date(fetched),
                    )
                )
            return messages
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ExternalServiceError(f"IMAP 连接失败：{exc}") from exc
        finally:
            if client is not None:
                try:
                    client.logout()
                except imaplib.IMAP4.error:
                    pass

    @staticmethod
    def _uid_validity(client: imaplib.IMAP4_SSL) -> str:
        response = client.response("UIDVALIDITY")
        if response and response[1]:
            return response[1][0].decode(errors="ignore")
        raise ExternalServiceError("IMAP 服务器未返回 UIDVALIDITY，无法安全去重")

    @classmethod
    def _send_client_identity(cls, client: imaplib.IMAP4_SSL) -> None:
        status, data = client.capability()
        if status != "OK":
            return
        capabilities = {
            token.upper()
            for value in (data or [])
            for token in value.split()
        }
        if b"ID" not in capabilities:
            return
        imaplib.Commands.setdefault("ID", ("AUTH", "SELECTED"))
        try:
            client._simple_command(
                "ID",
                '("name" "email-ai-assistant" "version" "1.0")',
            )
        except imaplib.IMAP4.error:
            return

    @staticmethod
    def _response_detail(data: list[bytes] | tuple[bytes, ...] | None) -> str:
        if not data:
            return ""
        return "; ".join(
            item.decode("utf-8", errors="replace")[:300]
            for item in data
            if isinstance(item, bytes) and item
        )

    @classmethod
    def _parse_message(
        cls,
        raw: bytes,
        folder: str,
        uid_validity: str,
        uid: str,
        received_at: datetime | None = None,
    ) -> FetchedEmail:
        message = email.message_from_bytes(raw)
        sender_name, sender_address = cls._sender(message)
        recipients = tuple(address for _, address in getaddresses(message.get_all("To", [])))
        sent_at = cls._date(message.get("Date"))
        body_text, attachments, links = cls._body(message)
        return FetchedEmail(
            folder=folder,
            uid_validity=uid_validity,
            uid=uid,
            message_id=message.get("Message-ID"),
            subject=cls._decode_header(message.get("Subject", "")),
            sender_name=sender_name,
            sender_address=sender_address,
            recipients=recipients,
            sent_at=sent_at,
            received_at=received_at or sent_at,
            body_text=body_text,
            attachment_names=tuple(attachments),
            extracted_links=report_links(links),
        )

    @staticmethod
    def _internal_date(fetched: list[object] | tuple[object, ...]) -> datetime | None:
        for part in fetched:
            if not isinstance(part, tuple) or not part or not isinstance(part[0], bytes):
                continue
            match = re.search(rb'INTERNALDATE "([^"]+)"', part[0], re.IGNORECASE)
            if match is None:
                continue
            try:
                return datetime.strptime(
                    match.group(1).decode("ascii"),
                    "%d-%b-%Y %H:%M:%S %z",
                )
            except (UnicodeDecodeError, ValueError):
                return None
        return None

    @staticmethod
    def _decode_header(value: str) -> str:
        try:
            return str(make_header(decode_header(value)))
        except (LookupError, UnicodeDecodeError):
            return value

    @classmethod
    def _sender(cls, message: Message) -> tuple[str | None, str]:
        decoded = cls._decode_header(message.get("From", ""))
        addresses = getaddresses([decoded])
        if not addresses:
            return None, decoded
        name, address = addresses[0]
        return name or None, address

    @staticmethod
    def _date(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = parsedate_to_datetime(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def _body(cls, message: Message) -> tuple[str, list[str], list[str]]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        attachments: list[str] = []
        for part in message.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            if filename:
                attachments.append(cls._decode_header(filename))
                continue
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(decoded)
            elif content_type == "text/html":
                html_parts.append(decoded)
        source = "\n".join(plain_parts) if plain_parts else "\n".join(html_parts)
        links = re.findall(r"https?://[^\s<>]+", "\n".join(plain_parts))
        for html in html_parts:
            soup = BeautifulSoup(html, "html.parser")
            links.extend(anchor.get("href") for anchor in soup.find_all("a") if anchor.get("href"))
        if html_parts and not plain_parts:
            source = BeautifulSoup(source, "html.parser").get_text(" ", strip=True)
        return source.strip(), attachments, list(report_links(links))
