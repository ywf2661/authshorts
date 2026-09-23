import json
from unittest.mock import MagicMock, patch

import pytest

from script_writer import pick_and_write_script
from config import Settings


def _settings():
    return Settings("ak", "gcid", "gcs", "yrt", "chan123", "https://t.me/x")


def _candidates():
    return [
        {"title": "기사1", "summary": "요약1", "link": "http://a", "published": (2026, 9, 23)},
        {"title": "기사2", "summary": "요약2", "link": "http://b", "published": (2026, 9, 23)},
    ]


def _mock_post_with_text(mock_post, text):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"content": [{"text": text}]}
    mock_post.return_value = mock_response


@patch("script_writer.requests.post")
def test_pick_and_write_script_parses_chosen_candidate(mock_post):
    _mock_post_with_text(
        mock_post,
        '"chosen_index": 1, "title": "쇼츠 제목", '
        '"sentences": ["문장1", "문장2"], "keywords": ["노트북"], '
        '"image_prompts": ["prompt1", "prompt2"]}',
    )

    result = pick_and_write_script(_settings(), _candidates())

    assert result["chosen_link"] == "http://b"
    assert result["title"] == "쇼츠 제목"
    assert result["sentences"] == ["문장1", "문장2"]
    assert result["keywords"] == ["노트북"]
    assert result["image_prompts"] == ["prompt1", "prompt2"]
    assert "chosen_index" not in result


@patch("script_writer.requests.post")
def test_pick_and_write_script_raises_on_invalid_json(mock_post):
    _mock_post_with_text(mock_post, "이건 JSON이 아님")

    with pytest.raises(ValueError):
        pick_and_write_script(_settings(), _candidates())


@patch("script_writer.requests.post")
def test_pick_and_write_script_raises_when_chosen_index_out_of_range(mock_post):
    _mock_post_with_text(
        mock_post,
        '"chosen_index": 5, "title": "t", "sentences": ["s"], "image_prompts": ["p"]}',
    )

    with pytest.raises(ValueError, match="범위를 벗어남"):
        pick_and_write_script(_settings(), _candidates())


@patch("script_writer.requests.post")
def test_pick_and_write_script_defaults_keywords_when_missing(mock_post):
    _mock_post_with_text(
        mock_post,
        '"chosen_index": 0, "title": "t", "sentences": ["s"], "image_prompts": ["p"]}',
    )

    result = pick_and_write_script(_settings(), _candidates())

    assert result["keywords"] == []


@patch("script_writer.requests.post")
def test_pick_and_write_script_raises_when_image_prompts_missing(mock_post):
    _mock_post_with_text(
        mock_post,
        '"chosen_index": 0, "title": "t", "sentences": ["s"]}',
    )

    with pytest.raises(ValueError, match="필수 필드 누락"):
        pick_and_write_script(_settings(), _candidates())


@patch("script_writer.requests.post")
def test_pick_and_write_script_raises_when_sentences_is_not_a_list(mock_post):
    _mock_post_with_text(
        mock_post,
        '"chosen_index": 0, "title": "t", "sentences": "한 문장", "image_prompts": ["p"]}',
    )

    with pytest.raises(ValueError):
        pick_and_write_script(_settings(), _candidates())


@patch("script_writer.requests.post")
def test_pick_and_write_script_raises_when_too_many_sentences(mock_post):
    payload = {
        "chosen_index": 0,
        "title": "t",
        "sentences": [f"문장{i}" for i in range(9)],
        "image_prompts": [f"prompt{i}" for i in range(9)],
    }
    _mock_post_with_text(mock_post, json.dumps(payload)[1:])  # pick_and_write_script prepends "{"

    with pytest.raises(ValueError):
        pick_and_write_script(_settings(), _candidates())


@patch("script_writer.requests.post")
def test_pick_and_write_script_raises_when_image_prompts_length_mismatch(mock_post):
    _mock_post_with_text(
        mock_post,
        '"chosen_index": 0, "title": "t", "sentences": ["s1", "s2"], '
        '"image_prompts": ["p1"]}',
    )

    with pytest.raises(ValueError):
        pick_and_write_script(_settings(), _candidates())
