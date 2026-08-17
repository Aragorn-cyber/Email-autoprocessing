import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import ApplicationSettings
from app.core.enums import ScanStatus, SuggestionType
from app.domain.entities import AnalyzedEmailReference, CompletedAnalysis, FetchedEmail
from app.domain.interfaces import EmailProvider, LanguageModelClient
from app.infrastructure.models import EmailAnalysisModel, EmailModel, MailboxAccountModel
from app.infrastructure.persistence import (
    ClassificationRepository,
    EmailRepository,
    MailboxAccountRepository,
    LocalReadMailRepository,
    ReportRepository,
    ScanRepository,
)
from app.services.analysis_service import EmailAnalysisService
from app.services.report_service import ReportService
from app.services.scoring_service import RuleScoringService


@dataclass(slots=True)
class AccountScanResult:
    account_id: int
    account_name: str
    fetched_count: int = 0
    processed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)
    analyzed: list[AnalyzedEmailReference] = field(default_factory=list)
    succeeded: bool = False


@dataclass(frozen=True, slots=True)
class ScanExecutionResult:
    scan_id: int
    report_id: int
    status: ScanStatus
    fetched_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    errors: tuple[dict[str, str], ...]


class ScanService:
    def __init__(
        self,
        session_factory,
        settings: ApplicationSettings,
        email_provider: EmailProvider,
        language_model: LanguageModelClient,
    ):
        self.session_factory = session_factory
        self.settings = settings
        self.email_provider = email_provider
        self.language_model = language_model
        self.semaphore = asyncio.Semaphore(settings.llm_concurrency)

    async def scan(self, account_ids: list[int] | None, window_days: int | None) -> ScanExecutionResult:
        with self.session_factory() as session:
            accounts = MailboxAccountRepository(session).list(active_only=True)
            if account_ids:
                allowed = set(account_ids)
                accounts = [account for account in accounts if account.id in allowed]
            effective_window = window_days or self.settings.default_scan_window_days
            scan = ScanRepository(session).start(effective_window, len(accounts))
            session.commit()
            scan_id = scan.id

        tasks = [self._scan_account(account, window_days) for account in accounts]
        results = await asyncio.gather(*tasks) if tasks else []
        fetched_count = sum(result.fetched_count for result in results)
        processed_count = sum(result.processed_count for result in results)
        skipped_count = sum(result.skipped_count for result in results)
        failed_count = sum(result.failed_count for result in results)
        errors = [
            {"account": result.account_name, "error": error}
            for result in results
            for error in result.errors
        ]
        has_completed_account = any(
            (result.succeeded and result.failed_count == 0)
            or result.processed_count
            or result.skipped_count
            for result in results
        )
        if errors and has_completed_account:
            status = ScanStatus.PARTIAL_SUCCESS
        elif errors:
            status = ScanStatus.FAILED
        else:
            status = ScanStatus.SUCCESS

        with self.session_factory() as session:
            scan_repository = ScanRepository(session)
            scan_repository.finish(
                scan_id,
                status,
                fetched_count,
                processed_count,
                skipped_count,
                failed_count,
                errors,
            )
            analyzed = self._reload_analyzed(session, results)
            report = ReportService(
                ReportRepository(session),
                EmailRepository(session),
                LocalReadMailRepository(session),
                ClassificationRepository(session),
            ).generate(scan_id, analyzed, errors)
            session.commit()
            return ScanExecutionResult(
                scan_id=scan_id,
                report_id=report.id,
                status=status,
                fetched_count=fetched_count,
                processed_count=processed_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                errors=tuple(errors),
            )

    async def _scan_account(
        self,
        account: MailboxAccountModel,
        requested_window_days: int | None,
    ) -> AccountScanResult:
        result = AccountScanResult(account_id=account.id, account_name=account.name)
        try:
            with self.session_factory() as session:
                stored_account = MailboxAccountRepository(session).get(account.id)
                connection = MailboxAccountRepository(session).connection_for(stored_account)
            window_days = requested_window_days or account.scan_window_days
            since = datetime.now(timezone.utc) - timedelta(days=window_days)
            fetched_emails = await self.email_provider.fetch_unread(connection, since)
            result.succeeded = True
            result.fetched_count = len(fetched_emails)
            tasks = [self._process_email(account.id, email) for email in fetched_emails]
            email_results = await asyncio.gather(*tasks)
            for status, email_id, analysis_id, error in email_results:
                if status == "processed":
                    result.processed_count += 1
                    result.analyzed.append(AnalyzedEmailReference(email_id, analysis_id))
                elif status == "skipped":
                    result.skipped_count += 1
                    if email_id is not None and analysis_id is not None:
                        result.analyzed.append(AnalyzedEmailReference(email_id, analysis_id))
                else:
                    result.failed_count += 1
                    result.errors.append(error or "邮件处理失败")
        except Exception as exc:
            result.failed_count += 1
            result.errors.append(str(exc))
        return result

    async def _process_email(
        self,
        account_id: int,
        email: FetchedEmail,
    ) -> tuple[str, int | None, int | None, str | None]:
        async with self.semaphore:
            with self.session_factory() as session:
                repository = EmailRepository(session)
                processed_reference = repository.processed_analysis_reference(account_id, email)
                if processed_reference is not None:
                    return (
                        "skipped",
                        processed_reference.email_id,
                        processed_reference.analysis_id,
                        None,
                    )
                classification_repository = ClassificationRepository(session)
                service = EmailAnalysisService(
                    classification_repository,
                    RuleScoringService(self.settings),
                    self.language_model,
                )
                try:
                    analysis = await service.analyze(email)
                    stored_email = repository.store_raw(account_id, email)
                    analysis_model = repository.save_completed_analysis(stored_email, analysis)
                    self._save_suggestions(classification_repository, stored_email.id, email, analysis)
                    repository.mark_processed(account_id, stored_email)
                    session.commit()
                    return "processed", stored_email.id, analysis_model.id, None
                except Exception as exc:
                    session.rollback()
                    return "failed", None, None, f"{email.subject or email.uid}：{exc}"

    @staticmethod
    def _save_suggestions(
        repository: ClassificationRepository,
        email_id: int,
        email: FetchedEmail,
        analysis: CompletedAnalysis,
    ) -> None:
        if analysis.source_id is None:
            repository.create_suggestion(
                SuggestionType.SOURCE,
                analysis.source_suggestion or analysis.source_name,
                email.sender_address.rsplit("@", 1)[-1] if "@" in email.sender_address else None,
                email_id,
                analysis.reason,
            )
        repository.create_suggestion(
            SuggestionType.CATEGORY,
            analysis.category_suggestion,
            None,
            email_id,
            analysis.reason,
        )

    @staticmethod
    def _reload_analyzed(
        session: Session,
        results: list[AccountScanResult],
    ) -> list[tuple[EmailModel, EmailAnalysisModel]]:
        analyzed: list[tuple[EmailModel, EmailAnalysisModel]] = []
        for result in results:
            for reference in result.analyzed:
                email = session.get(EmailModel, reference.email_id)
                analysis = session.get(EmailAnalysisModel, reference.analysis_id)
                if email and analysis:
                    _ = email.account
                    analyzed.append((email, analysis))
        return analyzed
