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
    if not response.ok:
        # invalid_grant / invalid_client 등 구글이 준 실제 사유를 로그에 남긴다
        token = settings.youtube_refresh_token
        # 토큰 값 자체는 찍지 않고 형태만 남긴다 (정상: '1//'로 시작, 100자 안팎)
        raise RuntimeError(
            f"토큰 갱신 실패 {response.status_code}: {response.text} "
            f"/ refresh_token 길이={len(token)}, '1//'로 시작={token.startswith('1//')}"
        )
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
            # AI 생성 이미지·음성 사용 → YouTube 합성 콘텐츠 표시 정책
            "status": {"privacyStatus": "public", "containsSyntheticMedia": True},
        },
        media_body=media,
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtu.be/{response['id']}"
