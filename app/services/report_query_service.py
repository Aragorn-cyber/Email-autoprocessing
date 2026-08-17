from app.infrastructure.persistence import ClassificationRepository, ReportRepository
from app.services.report_service import ReportService


class ReportQueryService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list_reports(self) -> list[dict]:
        with self.session_factory() as session:
            return [
                {
                    "id": report.id,
                    "scan_id": report.scan_id,
                    "created_at": report.created_at,
                    "overview": report.overview,
                }
                for report in ReportRepository(session).list()
            ]

    def latest_report(self) -> dict:
        with self.session_factory() as session:
            report = ReportRepository(session).latest()
            if report is None:
                return {"report": None}
            return {
                "id": report.id,
                "scan_id": report.scan_id,
                **ReportService.snapshot(report),
            }

    def get_report(self, report_id: int) -> dict:
        with self.session_factory() as session:
            report = ReportRepository(session).get(report_id)
            return {
                "id": report.id,
                "scan_id": report.scan_id,
                **ReportService.snapshot(report),
            }

    def list_categories(self):
        with self.session_factory() as session:
            return ClassificationRepository(session).active_categories()

    def list_suggestions(self) -> list[dict]:
        with self.session_factory() as session:
            suggestions = ClassificationRepository(session).list_suggestions(
                status="pending"
            )
            return [
                {
                    "id": suggestion.id,
                    "suggestion_type": suggestion.suggestion_type,
                    "proposed_name": suggestion.proposed_name,
                    "proposed_pattern": suggestion.proposed_pattern,
                    "email_id": suggestion.email_id,
                    "reason": suggestion.reason,
                    "status": suggestion.status,
                    "created_at": suggestion.created_at,
                }
                for suggestion in suggestions
            ]
