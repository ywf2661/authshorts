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
        google_client_id=os.environ["GOOGLE_CLIENT_ID"],
        google_client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        youtube_refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        youtube_channel_id=os.environ["YOUTUBE_CHANNEL_ID"],
        telegram_channel_url=os.environ["TELEGRAM_CHANNEL_URL"],
        hf_api_key=os.getenv("HF_API_KEY", ""),
    )
