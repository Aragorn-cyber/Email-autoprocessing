from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Generator[Session, None, None]:
    database = request.app.state.database
    with database.session_factory() as session:
        yield session

