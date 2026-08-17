from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import mimetypes
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import accounts, important_mails, mails, read_mails, reports, scans
from app.core.config import ApplicationSettings, get_settings
from app.core.exceptions import ApplicationError, ConflictError, ResourceNotFoundError
from app.infrastructure.database import Database
from app.infrastructure.imap.client import ImapEmailProvider
from app.infrastructure.llm.deepseek_client import DeepSeekLanguageModel
from app.infrastructure.persistence import ClassificationRepository
from app.services.account_service import AccountService
from app.services.mail_service import MailService
from app.services.report_query_service import ReportQueryService
from app.services.important_mail_service import ImportantMailService
from app.services.scan_service import ScanService
from app.services.read_mail_service import LocalReadMailService
from app.web.routes import router as web_router


# Windows can inherit a registry mapping that labels .js as text/plain. With
# nosniff enabled, browsers then refuse to execute every frontend interaction.
mimetypes.add_type("text/javascript", ".js", strict=True)


def create_application(
    settings: ApplicationSettings | None = None,
    email_provider=None,
    language_model=None,
) -> FastAPI:
    application_settings = settings or get_settings()
    database = Database(application_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.create_schema()
        with database.session_factory() as session:
            ClassificationRepository(session).seed_categories()
            session.commit()
        app.state.scan_service = ScanService(
            database.session_factory,
            application_settings,
            email_provider or ImapEmailProvider(),
            language_model or DeepSeekLanguageModel(application_settings),
        )
        app.state.read_mail_service = LocalReadMailService(database.session_factory)
        app.state.account_service = AccountService(database.session_factory)
        app.state.mail_service = MailService(database.session_factory)
        app.state.report_query_service = ReportQueryService(database.session_factory)
        app.state.important_mail_service = ImportantMailService(database.session_factory)
        yield

    app = FastAPI(title=application_settings.app_name, lifespan=lifespan)
    app.state.settings = application_settings
    app.state.database = database
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")
    app.include_router(web_router)
    app.include_router(accounts.router)
    app.include_router(scans.router)
    app.include_router(reports.router)
    app.include_router(mails.router)
    app.include_router(read_mails.router)
    app.include_router(important_mails.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.exception_handler(ResourceNotFoundError)
    async def not_found_handler(_: Request, exc: ResourceNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_: Request, exc: ApplicationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    return app


app = create_application()
