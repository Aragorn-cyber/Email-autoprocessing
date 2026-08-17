from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import ApplicationSettings


class DatabaseModel(DeclarativeBase):
    pass


class Database:
    def __init__(self, settings: ApplicationSettings):
        settings.ensure_local_directories()
        engine_options: dict[str, object] = {
            "connect_args": {"check_same_thread": False, "timeout": 30}
        }
        if settings.database_url in {"sqlite://", "sqlite:///:memory:"}:
            engine_options["poolclass"] = StaticPool
        self.engine = create_engine(settings.database_url, **engine_options)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        from app.infrastructure import models

        DatabaseModel.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        database_session = self.session_factory()
        try:
            yield database_session
        finally:
            database_session.close()
