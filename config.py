import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Settings:
    anthropic_api_key: str
    google_client_id: str
    google_client_secret: str
    youtube_refresh_token: str
    youtube_channel_id: str
    telegram_channel_url: str
    hf_api_key: str = ""
    # 사용 영상 봇(usage_bot.py)에서만 사용
    telegram_bot_token: str = ""
    telegram_owner_chat_id: str = ""
    # 선택 — 없으면 edge-tts(같은 현수 목소리)로 대체
    azure_speech_key: str = ""
    azure_speech_region: str = ""


def _clean(value: str) -> str:
    """Secrets 붙여넣기 때 섞이는 공백·줄바꿈·따옴표 제거."""
    return value.strip().strip("\"'").strip()


def load_settings() -> Settings:
    load_dotenv()
    required = [
        "ANTHROPIC_API_KEY",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "YOUTUBE_REFRESH_TOKEN",
        "YOUTUBE_CHANNEL_ID",
        "TELEGRAM_CHANNEL_URL",
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"필수 환경변수 누락: {', '.join(missing)}")

    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        google_client_id=_clean(os.environ["GOOGLE_CLIENT_ID"]),
        google_client_secret=_clean(os.environ["GOOGLE_CLIENT_SECRET"]),
        youtube_refresh_token=_clean(os.environ["YOUTUBE_REFRESH_TOKEN"]),
        youtube_channel_id=os.environ["YOUTUBE_CHANNEL_ID"],
        telegram_channel_url=os.environ["TELEGRAM_CHANNEL_URL"],
        hf_api_key=os.getenv("HF_API_KEY", ""),
        telegram_bot_token=_clean(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        telegram_owner_chat_id=_clean(os.getenv("TELEGRAM_OWNER_CHAT_ID", "")),
        azure_speech_key=_clean(os.getenv("AZURE_SPEECH_KEY", "")),
        azure_speech_region=_clean(os.getenv("AZURE_SPEECH_REGION", "")),
    )
