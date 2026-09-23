from unittest.mock import MagicMock, patch

from config import Settings
from youtube_api import refresh_access_token, upload_video


def _settings():
    return Settings("ak", "gcid", "gcs", "yrt", "chan123", "https://t.me/x")


@patch("youtube_api.requests.post")
def test_refresh_access_token_returns_token(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "new-token"}
    mock_post.return_value = mock_response

    token = refresh_access_token(_settings())

    assert token == "new-token"


@patch("youtube_api.MediaFileUpload")
@patch("youtube_api.build")
@patch("youtube_api.Credentials")
def test_upload_video_returns_watch_url_and_sets_public(
    mock_credentials, mock_build, mock_media
):
    mock_request = MagicMock()
    mock_request.next_chunk.side_effect = [(None, {"id": "abc123"})]
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_request
    mock_build.return_value = mock_youtube

    url = upload_video(_settings(), "token", "video.mp4", "제목", "설명")

    assert url == "https://youtu.be/abc123"
    insert_kwargs = mock_youtube.videos.return_value.insert.call_args.kwargs
    assert insert_kwargs["body"]["status"]["privacyStatus"] == "public"
    assert insert_kwargs["body"]["status"]["containsSyntheticMedia"] is True
    assert insert_kwargs["body"]["snippet"]["channelId"] == "chan123"
    assert insert_kwargs["body"]["snippet"]["title"] == "제목"


@patch("youtube_api.MediaFileUpload")
@patch("youtube_api.build")
@patch("youtube_api.Credentials")
def test_upload_video_truncates_title_over_100_chars(mock_credentials, mock_build, mock_media):
    mock_request = MagicMock()
    mock_request.next_chunk.side_effect = [(None, {"id": "abc123"})]
    mock_youtube = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_request
    mock_build.return_value = mock_youtube

    long_title = "가" * 150
    upload_video(_settings(), "token", "video.mp4", long_title, "설명")

    insert_kwargs = mock_youtube.videos.return_value.insert.call_args.kwargs
    assert len(insert_kwargs["body"]["snippet"]["title"]) == 100
