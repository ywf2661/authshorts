import json
from unittest.mock import MagicMock, patch

import pytest

from script_writer import write_script
from config import Settings


def _settings():
    return Settings("ak", "gcid", "gcs", "yrt", "chan123", "https://t.me/x")


def _product():
    return {"productName": "몬스터겔 투명 케이스", "productUrl": "http://a"}


def _mock_post_with_text(mock_post, text):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"content": [{"text": text}]}
    mock_post.return_value = mock_response


@patch("script_writer.requests.post")
def test_write_script_parses_response(mock_post):
    _mock_post_with_text(
        mock_post,
        '"title": "쇼츠 제목", '
        '"sentences": ["문장1", "문장2"], "keywords": ["노트북"], '
        '"image_prompts": ["prompt1", "prompt2"]}',
    )

    result = write_script(_settings(), _product())

    assert "몬스터겔 투명 케이스" in mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert result["title"] == "쇼츠 제목"
    assert result["sentences"] == ["문장1", "문장2"]
    assert result["keywords"] == ["노트북"]
    assert result["image_prompts"] == ["prompt1", "prompt2"]


@patch("script_writer.requests.post")
def test_write_script_raises_on_invalid_json(mock_post):
    _mock_post_with_text(mock_post, "이건 JSON이 아님")

    with pytest.raises(ValueError):
        write_script(_settings(), _product())


@patch("script_writer.requests.post")
def test_write_script_defaults_keywords_when_missing(mock_post):
    _mock_post_with_text(
        mock_post,
        '"title": "t", "sentences": ["s"], "image_prompts": ["p"]}',
    )

    result = write_script(_settings(), _product())

    assert result["keywords"] == []


@patch("script_writer.requests.post")
def test_write_script_raises_when_image_prompts_missing(mock_post):
    _mock_post_with_text(
        mock_post,
        '"title": "t", "sentences": ["s"]}',
    )

    with pytest.raises(ValueError, match="필수 필드 누락"):
        write_script(_settings(), _product())


@patch("script_writer.requests.post")
def test_write_script_raises_when_sentences_is_not_a_list(mock_post):
    _mock_post_with_text(
        mock_post,
        '"title": "t", "sentences": "한 문장", "image_prompts": ["p"]}',
    )

    with pytest.raises(ValueError):
        write_script(_settings(), _product())


@patch("script_writer.requests.post")
def test_write_script_raises_when_too_many_sentences(mock_post):
    payload = {
        "title": "t",
        "sentences": [f"문장{i}" for i in range(9)],
        "image_prompts": [f"prompt{i}" for i in range(9)],
    }
    _mock_post_with_text(mock_post, json.dumps(payload)[1:])  # write_script prepends "{"

    with pytest.raises(ValueError):
        write_script(_settings(), _product())


@patch("script_writer.requests.post")
def test_write_script_raises_when_image_prompts_length_mismatch(mock_post):
    _mock_post_with_text(
        mock_post,
        '"title": "t", "sentences": ["s1", "s2"], '
        '"image_prompts": ["p1"]}',
    )

    with pytest.raises(ValueError):
        write_script(_settings(), _product())


def _clip_frames():
    return [(0.0, b"jpg0"), (2.0, b"jpg1")]


@patch("script_writer.requests.post")
def test_write_clip_script_returns_sentences_and_starts(mock_post):
    from script_writer import write_clip_script

    _mock_post_with_text(
        mock_post,
        '"title": "t", "segments": [{"start": 0, "sentence": "s1"}, {"start": 2, "sentence": "s2"}], '
        '"keywords": ["케이스"]}',
    )

    result = write_clip_script(_settings(), _product(), _clip_frames(), 5.0)

    assert result["sentences"] == ["s1", "s2"]
    assert result["starts"] == [0.0, 2.0]
    content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert [c["type"] for c in content] == ["text", "image", "text", "image", "text"]


@patch("script_writer.requests.post")
def test_write_clip_script_rejects_start_outside_video(mock_post):
    from script_writer import write_clip_script

    _mock_post_with_text(mock_post, '"title": "t", "segments": [{"start": 9, "sentence": "s"}]}')

    with pytest.raises(ValueError, match="범위"):
        write_clip_script(_settings(), _product(), _clip_frames(), 5.0)
