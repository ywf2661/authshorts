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
    settings: Settings, access_token: str, video_path: str, title: str, description: str,
    tags: list[str] = (), synthetic: bool = True,
) -> str:
    """영상을 채널에 공개(public)로 업로드하고 시청 URL을 반환한다.

    synthetic: YouTube '변경되거나 합성된 콘텐츠' 표시. 실제 상품 사진만 쓰는 TOP3 봇은 False.
    """
    title = title[:100]  # YouTube snippet.title 최대 100자
    credentials = Credentials(token=access_token)
    youtube = build("youtube", "v3", credentials=credentials)
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(
        part="snippet,status,paidProductPlacementDetails",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "channelId": settings.youtube_channel_id,
                # 검색용 숨은 태그 (설명란 해시태그와 같은 목록)
                "tags": list(tags),
                "categoryId": "26",  # 노하우/스타일
                "defaultLanguage": "ko",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": synthetic,
            },
            # 쿠팡 파트너스 수수료 → '유료 광고 포함' 라벨
            "paidProductPlacementDetails": {"hasPaidProductPlacement": True},
        },
        media_body=media,
    )
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtu.be/{response['id']}"
