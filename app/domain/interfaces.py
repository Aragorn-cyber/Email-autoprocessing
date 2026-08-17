from datetime import datetime
from typing import Protocol

from app.domain.entities import FetchedEmail, MailboxConnection, SemanticAnalysis


class EmailProvider(Protocol):
    async def fetch_unread(
        self,
        connection: MailboxConnection,
        since: datetime,
    ) -> list[FetchedEmail]: ...


class LanguageModelClient(Protocol):
    async def analyze_email(
        self,
        email: FetchedEmail,
        category_names: tuple[str, ...],
    ) -> SemanticAnalysis: ...

