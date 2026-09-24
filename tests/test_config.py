import pytest

from config import load_settings


def test_load_settings_raises_when_keys_missing(monkeypatch):
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: None)
    for key in [
        "ANTHROPIC_API_KEY",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
        "YOUTUBE_CHANNEL_ID",
        "TELEGRAM_CHANNEL_URL",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="필수 환경변수 누락"):
        load_settings()


def test_load_settings_reads_env(monkeypatch):
    monkeypatch.setattr("config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "gcid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "gcs")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "yrt")
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "chan123")
    monkeypatch.setenv("TELEGRAM_CHANNEL_URL", "https://t.me/x")

    settings = load_settings()

    assert settings.anthropic_api_key == "ak"
    assert settings.youtube_channel_id == "chan123"
