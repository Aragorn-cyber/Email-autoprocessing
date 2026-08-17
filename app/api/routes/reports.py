from fastapi import APIRouter, Request

from app.api.schemas import CategoryResponse


router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/reports")
def list_reports(request: Request):
    return request.app.state.report_query_service.list_reports()


@router.get("/reports/latest")
def latest_report(request: Request):
    return request.app.state.report_query_service.latest_report()


@router.get("/reports/{report_id}")
def get_report(report_id: int, request: Request):
    return request.app.state.report_query_service.get_report(report_id)


@router.get("/categories", response_model=list[CategoryResponse])
def list_categories(request: Request):
    return request.app.state.report_query_service.list_categories()


@router.get("/suggestions")
def list_suggestions(request: Request):
    return request.app.state.report_query_service.list_suggestions()
