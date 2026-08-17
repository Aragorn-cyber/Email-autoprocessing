import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.models import ReportModel


class ReportRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        scan_id: int,
        earliest_email_at: datetime | None,
        latest_email_at: datetime | None,
        overview: str,
        snapshot: dict[str, object],
    ) -> ReportModel:
        report = ReportModel(
            scan_id=scan_id,
            earliest_email_at=earliest_email_at,
            latest_email_at=latest_email_at,
            overview=overview,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
        )
        self.session.add(report)
        self.session.flush()
        return report

    def get(self, report_id: int) -> ReportModel:
        report = self.session.get(ReportModel, report_id)
        if report is None:
            raise ResourceNotFoundError(f"报告 {report_id} 不存在")
        return report

    def latest(self) -> ReportModel | None:
        return self.session.scalar(select(ReportModel).order_by(ReportModel.created_at.desc()))

    def list(self, limit: int = 50) -> list[ReportModel]:
        return list(
            self.session.scalars(
                select(ReportModel).order_by(ReportModel.created_at.desc()).limit(limit)
            )
        )
