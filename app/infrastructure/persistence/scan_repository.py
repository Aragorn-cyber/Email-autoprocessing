import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.enums import ScanStatus
from app.core.exceptions import ResourceNotFoundError
from app.infrastructure.models import ScanRecordModel


class ScanRepository:
    def __init__(self, session: Session):
        self.session = session

    def start(self, window_days: int, account_count: int) -> ScanRecordModel:
        scan = ScanRecordModel(
            window_days=window_days,
            account_count=account_count,
            status=ScanStatus.RUNNING.value,
        )
        self.session.add(scan)
        self.session.flush()
        return scan

    def finish(
        self,
        scan_id: int,
        status: ScanStatus,
        fetched_count: int,
        processed_count: int,
        skipped_count: int,
        failed_count: int,
        errors: list[dict[str, str]],
    ) -> ScanRecordModel:
        scan = self.session.get(ScanRecordModel, scan_id)
        if scan is None:
            raise ResourceNotFoundError(f"扫描记录 {scan_id} 不存在")
        scan.status = status.value
        scan.finished_at = datetime.now(timezone.utc)
        scan.fetched_count = fetched_count
        scan.processed_count = processed_count
        scan.skipped_count = skipped_count
        scan.failed_count = failed_count
        scan.errors_json = json.dumps(errors, ensure_ascii=False)
        return scan
