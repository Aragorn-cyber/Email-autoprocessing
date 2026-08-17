from app.infrastructure.credentials import EnvironmentCredentialProvider


def test_credential_provider_reads_arbitrary_name_from_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("CUSTOM_MAIL_PASSWORD=secret-value\n", encoding="utf-8")
    monkeypatch.delenv("CUSTOM_MAIL_PASSWORD", raising=False)

    provider = EnvironmentCredentialProvider(env_file)

    assert provider.get("CUSTOM_MAIL_PASSWORD") == "secret-value"
