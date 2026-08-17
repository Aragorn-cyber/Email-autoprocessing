from fastapi import APIRouter, Request

from app.api.schemas import ScanRequest, ScanResponse


router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("", response_model=ScanResponse)
async def start_scan(
    payload: ScanRequest,
    request: Request,
):
    service = request.app.state.scan_service
    result = await service.scan(payload.account_ids, payload.window_days)
    return ScanResponse(
        scan_id=result.scan_id,
        report_id=result.report_id,
        status=result.status.value,
        fetched_count=result.fetched_count,
        processed_count=result.processed_count,
        skipped_count=result.skipped_count,
        failed_count=result.failed_count,
        errors=list(result.errors),
    )
