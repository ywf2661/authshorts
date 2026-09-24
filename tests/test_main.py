import json
from unittest.mock import MagicMock, patch

import pytest

import main
from config import Settings

JPG = b"\xff\xd8" + b"rest"
BUNDLE_TEXT = (
    "# 주석\n"
    "옛날 상품 | http://old\n"
    "[3만원 이하 방한템]\n"
    "난방텐트 | http://a | http://a1.jpg http://a2.jpg | 포인트: 침대 위 텐트\n"
    "극세사 담요 | http://b | http://b1.jpg | 세탁기 가능\n"
    "문풍지 | http://c | http://c1.jpg | 외풍 차단\n"
    "[혼자]\n"
    "하나뿐 | http://x | http://x.jpg | 포인트: 하나\n"
    "[자취 주방템]\n"
    "도마 | http://d | http://d.jpg | 포인트: 칼자국 안 남음\n"
    "수세미 | http://e | http://e.jpg |\n"
)


def _settings():
    return Settings("ak", "gcid", "gcs", "yrt", "chan", "https://t.me/x",
                    telegram_bot_token="tok", telegram_owner_chat_id="1")


def test_parse_product_line_reads_images_and_point():
    product = main.parse_product_line(
        "텐트 | http://a | http://1.jpg http://2.jpg http://3.jpg http://4.jpg | 포인트: 따뜻함"
    )

    assert product == {"productName": "텐트", "productUrl": "http://a",
                       "images": ["http://1.jpg", "http://2.jpg", "http://3.jpg"], "point": "따뜻함"}
    # 사용 영상 봇 캡션 형식
    assert main.parse_product_line("케이스 | http://x")["point"] == ""
    assert main.parse_product_line("링크 없는 줄") is None


def test_load_bundles_groups_by_topic_and_drops_bad_ones(tmp_path):
    path = tmp_path / "products.txt"
    path.write_text(BUNDLE_TEXT, encoding="utf-8")

    bundles = main.load_bundles(str(path))

    assert [b["topic"] for b in bundles] == ["3만원 이하 방한템", "자취 주방템"]
    assert [p["productName"] for p in bundles[0]["products"]] == ["난방텐트", "극세사 담요", "문풍지"]
    assert bundles[0]["products"][0]["images"] == ["http://a1.jpg", "http://a2.jpg"]
    assert bundles[1]["products"][1]["point"] == ""


def test_real_products_file_parses():
    main.load_bundles(main.PRODUCTS_PATH)


def test_original_image_url_upgrades_coupang_thumbnail():
    thumb = "https://thumbnail.coupangcdn.com/thumbnails/remote/640x640ex/image/vendor_inventory/ab/cd.jpg"

    assert main.original_image_url(thumb) == "https://image1.coupangcdn.com/image/vendor_inventory/ab/cd.jpg"
    assert main.original_image_url("http://other/x.jpg") == "http://other/x.jpg"


def _beat(kind, product, rank, text="대사 하나"):
    return {"kind": kind, "product": product, "rank": rank, "text": text}


SCRIPT = {
    "title": "방한템 TOP3",
    "hook_lines": ["안 쓰면", "고생"],
    "labels": ["난방텐트", "담요", "문풍지"],
    "beats": [
        _beat("hook", 0, 0), _beat("item", 2, 3), _beat("item", 1, 2), _beat("item", 1, 2),
        _beat("reveal", 0, 1), _beat("reveal", 0, 1), _beat("outro", 0, 0),
    ],
    "keywords": ["방한템"],
}
TIMINGS = [{"start": float(i), "end": float(i + 1), "words": [(i + 0.1, i + 0.9), (i + 0.9, i + 1.0)]}
           for i in range(7)]


def test_compose_top_builds_scenes_overlays_and_sfx():
    photos = [["p0.jpg"], ["p1.jpg"], ["p2.jpg"]]
    style = {"hook": "quiz", "palette": 0}
    with patch("main.sfx_path", side_effect=lambda name: f"{name}.mp3"):
        scenes, events, sfx = main.compose_top(SCRIPT, "방한템", photos, TIMINGS, 12, style, 7.0)

    palette = main.PALETTES[0]
    assert scenes[0]["blur"] and scenes[0]["photos"] == ["p0.jpg"] and scenes[0]["bg"] == palette[0]
    assert scenes[1]["bg"] == palette[2] and not scenes[1]["blur"]
    assert scenes[4]["focus"] and not scenes[3]["focus"]
    text = "\n".join(events)
    assert "방한템 TOP3" in text
    assert "3위 · 문풍지" in text and "1위 · 난방텐트" in text
    assert text.count("2위 · 담요") == 1  # 같은 순위가 이어지면 뱃지는 한 번
    assert "제품은 프로필 링크 #12" in text
    assert text.count("쿠팡 파트너스") == 2
    assert sfx == [(1.0, "whoosh.mp3"), (2.0, "whoosh.mp3"), (4.0, "ding.mp3")]


@pytest.fixture
def env(tmp_path, monkeypatch):
    products = tmp_path / "products.txt"
    products.write_text(BUNDLE_TEXT, encoding="utf-8")
    monkeypatch.setattr(main, "PRODUCTS_PATH", str(products))
    monkeypatch.setattr(main, "POSTED_IDS_PATH", str(tmp_path / "ids.json"))
    monkeypatch.setattr(main, "POSTED_VIDEOS_PATH", str(tmp_path / "videos.json"))
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(main, "load_settings", _settings)
    calls = MagicMock()
    for name, value in [
        ("refresh_access_token", "at"), ("download_image", JPG), ("write_top_script", SCRIPT),
        ("synthesize", None), ("probe_duration", 6.5), ("render", "final.mp4"),
        ("pick_bgm", None), ("upload_video", "https://youtu.be/v"), ("notify", None),
    ]:
        mock = getattr(calls, name)
        mock.return_value = value
        monkeypatch.setattr(main, name, mock)
    return calls


def test_run_uploads_first_bundle_and_records_it(env):
    assert main.run() == "https://youtu.be/v"

    order = [c[0] for c in env.mock_calls]
    assert order.index("refresh_access_token") < order.index("write_top_script")
    kwargs = env.upload_video.call_args.kwargs
    assert kwargs["synthetic"] is False
    assert env.upload_video.call_args.args[3] == "[광고] 방한템 TOP3"
    assert "프로필 링크 #1" in env.upload_video.call_args.args[4]
    records = json.load(open(main.POSTED_VIDEOS_PATH, encoding="utf-8"))
    assert records[0]["number"] == 1 and records[0]["topic"] == "3만원 이하 방한템"
    assert records[0]["products"][2] == {"name": "문풍지", "label": "문풍지", "link": "http://c"}
    assert "남은 묶음 1개" in env.notify.call_args.args[1]  # 재고 부족 알림

    # 같은 날 다시 돌리면 하루 1편 상한
    env.reset_mock()
    assert main.run() is None
    env.write_top_script.assert_not_called()


def test_run_skips_bundle_with_missing_point(env):
    ids = main.bundle_key(main.load_bundles(main.PRODUCTS_PATH)[0])
    json.dump([ids], open(main.POSTED_IDS_PATH, "w"))

    assert main.run() is None
    assert "포인트" in env.notify.call_args.args[1] and "수세미" in env.notify.call_args.args[1]
    env.write_top_script.assert_not_called()


def test_run_skips_when_photos_fail(env):
    env.download_image.return_value = None

    assert main.run() is None
    assert "사진" in env.notify.call_args.args[1]
    env.write_top_script.assert_not_called()


def test_run_skips_when_script_rejected(env):
    env.write_top_script.side_effect = main.ScriptRejected("1인칭")

    assert main.run() is None
    assert "대본 검사" in env.notify.call_args.args[1]
    env.upload_video.assert_not_called()


def test_run_notifies_when_no_bundles_left(env, tmp_path):
    (tmp_path / "products.txt").write_text("# 비었음\n", encoding="utf-8")

    assert main.run() is None
    assert "남은 묶음이 없어" in env.notify.call_args.args[1]
