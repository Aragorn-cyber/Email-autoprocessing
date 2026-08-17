from fastapi.testclient import TestClient

from app.core.config import ApplicationSettings
from app.main import create_application
from tests.conftest import FakeEmailProvider


def test_application_starts_without_llm_key_for_initial_configuration(tmp_path):
    settings = ApplicationSettings(
        database_url=f"sqlite:///{tmp_path / 'no-key.db'}",
        llm_api_key="",
    )
    app = create_application(settings, FakeEmailProvider())

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
