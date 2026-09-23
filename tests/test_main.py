from unittest.mock import MagicMock, mock_open, patch

import pytest

import main


def _feed_entries():
    return [
        {
            "title": "t1", "summary": "s1", "link": "http://a",
            "published": (2026, 9, 20, 0, 0, 0, 0, 0, 0),
        },
        {
            "title": "t2", "summary": "s2", "link": "http://b",
            "published": (2026, 9, 22, 0, 0, 0, 0, 0, 0),
        },
        {
            "title": "t3", "summary": "s3", "link": "http://c",
            "published": (2026, 9, 21, 0, 0, 0, 0, 0, 0),
        },
    ]


def test_pick_candidates_returns_unposted_sorted_by_recency_limited():
    entries = _feed_entries()
    posted = {main.hash_link("http://a")}

    result = main._pick_candidates(entries, posted, limit=2)

    assert [e["link"] for e in result] == ["http://b", "http://c"]


@patch("main.save_posted_ids")
@patch("main.upload_video")
@patch("main.refresh_access_token")
@patch("main.build_description")
@patch("main.search_products")
@patch("main.assemble_video")
@patch("main.synthesize")
@patch("main.save_generated_image")
@patch("main.generate_image")
@patch("main.pick_and_write_script")
@patch("main.load_posted_ids")
@patch("main.fetch_feed_entries")
@patch("main.load_settings")
@patch("builtins.open", new_callable=mock_open, read_data="http://feed1\n")
def test_run_uploads_video_for_chosen_candidate(
    mock_file,
    mock_load_settings,
    mock_fetch,
    mock_load_posted,
    mock_pick_script,
    mock_generate_image,
    mock_save_image,
    mock_synth,
    mock_assemble,
    mock_search,
    mock_build_description,
    mock_refresh,
    mock_upload,
    mock_save_posted,
):
    settings = MagicMock()
    settings.telegram_channel_url = "https://t.me/x"
    mock_load_settings.return_value = settings
    mock_fetch.return_value = _feed_entries()
    mock_load_posted.return_value = set()
    mock_pick_script.return_value = {
        "chosen_link": "http://b",
        "title": "제목",
        "sentences": ["문장1", "문장2"],
        "keywords": ["노트북"],
        "image_prompts": ["prompt1", "prompt2"],
    }
    mock_generate_image.side_effect = [b"\x89PNG\r\n\x1a\n" + b"rest", None]
    mock_save_image.return_value = "work/image_1.png"
    mock_synth.return_value = ["work/1.mp3", "work/2.mp3"]
    mock_assemble.return_value = "work/final.mp4"
    mock_search.return_value = []
    mock_build_description.return_value = "설명"
    mock_refresh.return_value = "token"
    mock_upload.return_value = "https://youtu.be/abc123"

    result = main.run()

    assert result == "https://youtu.be/abc123"
    mock_save_posted.assert_called_once()
    mock_search.assert_called_once_with("노트북")
    mock_generate_image.assert_any_call(settings, "prompt1")
    mock_generate_image.assert_any_call(settings, "prompt2")
    mock_assemble.assert_called_once()
    assemble_args = mock_assemble.call_args[0]
    assert assemble_args[0] == ["문장1", "문장2"]
    assert assemble_args[1] == ["work/1.mp3", "work/2.mp3"]
    assert assemble_args[2] == ["work/image_1.png", None]
    mock_build_description.assert_called_once_with(
        "문장1 문장2", [], "https://t.me/x", ["노트북"]
    )
    mock_upload.assert_called_once_with(settings, "token", "work/final.mp4", "제목", "설명")


@patch("main.save_posted_ids")
@patch("main.upload_video")
@patch("main.refresh_access_token")
@patch("main.build_description")
@patch("main.search_products")
@patch("main.assemble_video")
@patch("main.synthesize")
@patch("main.save_generated_image")
@patch("main.generate_image")
@patch("main.pick_and_write_script")
@patch("main.load_posted_ids")
@patch("main.fetch_feed_entries")
@patch("main.load_settings")
@patch("builtins.open", new_callable=mock_open, read_data="http://feed1\n")
def test_run_falls_back_to_none_when_image_bytes_are_not_a_valid_image(
    mock_file,
    mock_load_settings,
    mock_fetch,
    mock_load_posted,
    mock_pick_script,
    mock_generate_image,
    mock_save_image,
    mock_synth,
    mock_assemble,
    mock_search,
    mock_build_description,
    mock_refresh,
    mock_upload,
    mock_save_posted,
):
    settings = MagicMock()
    settings.telegram_channel_url = "https://t.me/x"
    mock_load_settings.return_value = settings
    mock_fetch.return_value = _feed_entries()
    mock_load_posted.return_value = set()
    mock_pick_script.return_value = {
        "chosen_link": "http://b",
        "title": "제목",
        "sentences": ["문장1"],
        "keywords": [],
        "image_prompts": ["prompt1"],
    }
    mock_generate_image.return_value = b"not an image"
    mock_synth.return_value = ["work/1.mp3"]
    mock_assemble.return_value = "work/final.mp4"
    mock_search.return_value = []
    mock_build_description.return_value = "설명"
    mock_refresh.return_value = "token"
    mock_upload.return_value = "https://youtu.be/abc123"

    main.run()

    mock_save_image.assert_not_called()
    assemble_args = mock_assemble.call_args[0]
    assert assemble_args[2] == [None]


@patch("main.load_posted_ids")
@patch("main.fetch_feed_entries")
@patch("main.load_settings")
@patch("builtins.open", new_callable=mock_open, read_data="http://feed1\n")
def test_run_returns_none_when_no_entries(
    mock_file, mock_load_settings, mock_fetch, mock_load_posted
):
    mock_load_settings.return_value = object()
    mock_fetch.return_value = []
    mock_load_posted.return_value = set()

    result = main.run()

    assert result is None


@patch("main.load_posted_ids")
@patch("main.fetch_feed_entries")
@patch("main.load_settings")
@patch("builtins.open", new_callable=mock_open, read_data="http://feed1\n")
def test_run_returns_none_when_all_entries_already_posted(
    mock_file, mock_load_settings, mock_fetch, mock_load_posted
):
    entries = _feed_entries()
    mock_load_settings.return_value = object()
    mock_fetch.return_value = entries
    mock_load_posted.return_value = {main.hash_link(e["link"]) for e in entries}

    result = main.run()

    assert result is None


@patch("main.upload_video")
@patch("main.save_posted_ids")
@patch("main.refresh_access_token")
@patch("main.build_description")
@patch("main.search_products")
@patch("main.assemble_video")
@patch("main.synthesize")
@patch("main.save_generated_image")
@patch("main.generate_image")
@patch("main.pick_and_write_script")
@patch("main.load_posted_ids")
@patch("main.fetch_feed_entries")
@patch("main.load_settings")
@patch("builtins.open", new_callable=mock_open, read_data="http://feed1\n")
def test_run_does_not_save_posted_ids_when_upload_fails(
    mock_file,
    mock_load_settings,
    mock_fetch,
    mock_load_posted,
    mock_pick_script,
    mock_generate_image,
    mock_save_image,
    mock_synth,
    mock_assemble,
    mock_search,
    mock_build_description,
    mock_refresh,
    mock_save_posted,
    mock_upload,
):
    settings = MagicMock()
    settings.telegram_channel_url = "https://t.me/x"
    mock_load_settings.return_value = settings
    mock_fetch.return_value = _feed_entries()
    mock_load_posted.return_value = set()
    mock_pick_script.return_value = {
        "chosen_link": "http://b",
        "title": "제목",
        "sentences": ["문장1"],
        "keywords": [],
        "image_prompts": ["prompt1"],
    }
    mock_generate_image.return_value = b"\x89PNG\r\n\x1a\n" + b"rest"
    mock_save_image.return_value = "work/image_1.png"
    mock_synth.return_value = ["work/1.mp3"]
    mock_assemble.return_value = "work/final.mp4"
    mock_build_description.return_value = "설명"
    mock_refresh.return_value = "token"
    mock_upload.side_effect = RuntimeError("quota exceeded")

    with pytest.raises(RuntimeError):
        main.run()

    mock_save_posted.assert_not_called()
