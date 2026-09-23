from unittest.mock import MagicMock, patch

import pytest

import usage_bot
from config import Settings

OWNER = "111"


def _settings():
    return Settings("ak", "gcid", "gcs", "yrt", "chan", "https://t.me/x",
                    telegram_bot_token="tok", telegram_owner_chat_id=OWNER)


def _msg(chat_id=OWNER, **extra):
    return {"message_id": 5, "chat": {"id": int(chat_id)}, **extra}


def _sent_texts(tg):
    return [c.kwargs["text"] for c in tg.call_args_list if c.args[1] == "sendMessage"]


def test_preview_caption_round_trips():
    product = {"productName": "투명 케이스", "productUrl": "https://link.coupang.com/a/x"}
    caption = usage_bot._preview_caption("잇템 제목", product, "요약: 문장", "sneaky-snitch")

    title, parsed, summary, bgm_name = usage_bot._parse_preview_caption(caption)

    assert title == "잇템 제목"
    assert parsed["productName"] == "투명 케이스"
    assert parsed["productUrl"] == "https://link.coupang.com/a/x"
    assert summary == "요약: 문장"
    assert bgm_name == "sneaky-snitch"


def test_parse_preview_caption_rejects_garbage():
    with pytest.raises(ValueError):
        usage_bot._parse_preview_caption("아무 말")


@patch("usage_bot._make_preview")
@patch("usage_bot._tg")
def test_stranger_gets_chat_id_and_nothing_is_processed(tg, make_preview):
    usage_bot._handle_message(_settings(), _msg("999", video={"file_id": "f"}, caption="a | http://x"))

    assert "999" in _sent_texts(tg)[0]
    make_preview.assert_not_called()


@patch("usage_bot._make_preview")
@patch("usage_bot._tg")
def test_video_without_product_caption_gets_help(tg, make_preview):
    usage_bot._handle_message(_settings(), _msg(video={"file_id": "f"}, caption="캡션 없음"))

    assert _sent_texts(tg) == [usage_bot.HELP_TEXT]
    make_preview.assert_not_called()


@patch("usage_bot._make_preview")
@patch("usage_bot._tg")
def test_oversized_video_is_rejected(tg, make_preview):
    video = {"file_id": "f", "file_size": 21 * 1024 * 1024}
    usage_bot._handle_message(_settings(), _msg(video=video, caption="케이스 | http://x"))

    assert "20MB" in _sent_texts(tg)[0]
    make_preview.assert_not_called()


@patch("usage_bot._make_preview")
@patch("usage_bot._tg")
def test_video_sent_as_file_is_accepted(tg, make_preview):
    doc = {"file_id": "f", "file_unique_id": "u", "mime_type": "video/mp4", "file_size": 1000}
    usage_bot._handle_message(_settings(), _msg(document=doc, caption="케이스 | http://x"))

    make_preview.assert_called_once()
    assert make_preview.call_args.args[2] == doc
    assert make_preview.call_args.args[3]["productName"] == "케이스"


def _callback(data, from_id=OWNER):
    caption = usage_bot._preview_caption(
        "제목", {"productName": "케이스", "productUrl": "http://x"}, "요약", "sneaky-snitch"
    )
    return {
        "id": "q1", "data": data, "from": {"id": int(from_id)},
        "message": _msg(video={"file_id": "edited"}, caption=caption),
    }


@patch("usage_bot.upload_video", return_value="https://youtu.be/v")
@patch("usage_bot.refresh_access_token", return_value="at")
@patch("usage_bot._download", return_value="work/final.mp4")
@patch("usage_bot._tg")
def test_upload_button_uploads_with_ad_title_once(tg, download, refresh, upload):
    handled = set()
    usage_bot._handle_callback(_settings(), _callback("upload"), handled)
    usage_bot._handle_callback(_settings(), _callback("upload"), handled)  # 연타

    upload.assert_called_once()
    assert upload.call_args.args[3] == "[광고] 제목"
    assert "http://x" in upload.call_args.args[4]
    assert "Sneaky Snitch" in upload.call_args.args[4]  # 음악 저작자 표시
    assert "https://youtu.be/v" in _sent_texts(tg)[-1]


@patch("usage_bot.upload_video")
@patch("usage_bot._tg")
def test_cancel_button_does_not_upload(tg, upload):
    usage_bot._handle_callback(_settings(), _callback("cancel"), set())

    upload.assert_not_called()
    assert _sent_texts(tg) == ["취소했어요."]


@patch("usage_bot.upload_video")
@patch("usage_bot._tg")
def test_callback_from_stranger_is_ignored(tg, upload):
    usage_bot._handle_callback(_settings(), _callback("upload", from_id="999"), set())

    upload.assert_not_called()
    tg.assert_not_called()


@patch("usage_bot._handle_message", side_effect=RuntimeError("터짐"))
@patch("usage_bot._tg")
@patch("usage_bot.load_settings")
def test_run_confirms_updates_before_handling_and_reports_errors(load, tg, handle):
    load.return_value = _settings()
    tg.side_effect = lambda s, method, **kw: (
        [{"update_id": 7, "message": _msg()}] if method == "getUpdates" and "offset" not in kw else True
    )

    usage_bot.run()

    methods = [c.args[1] for c in tg.call_args_list]
    assert methods[:2] == ["getUpdates", "getUpdates"]
    assert tg.call_args_list[1].kwargs["offset"] == 8
    assert "처리 실패: 터짐" in _sent_texts(tg)[0]
