import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import Settings

TOKEN_URL = "https://oauth2.googleapis.com/token"


def refresh_access_token(settings: Settings) -> str:
    """refresh_token으로 새 access_token을 발급받는다."""
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": settings.youtube_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def upload_video(
    settings: Settings, access_token: str, video_path: str, title: str, description: str
) -> str:
    """영상을 채널에 공개(public)로 업로드하고 시청 URL을 반환한다."""
    title = title[:100]  # YouTube snippet.title 최대 100자
    credentials = Credentials(token=access_token)
    youtube = build("youtube", "v3", credentials=credentials)
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "channelId": settings.youtube_channel_id,
            },
            "status": {"privacyStatus": "public"},
        },
        media_body=media,
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtu.be/{response['id']}"
