from unittest.mock import MagicMock, patch

import pytest

import main

PNG = b"\x89PNG\r\n\x1a\n" + b"rest"
JPG = b"\xff\xd8" + b"rest"


def _products():
    return [
        {"productName": "A", "productUrl": "http://a", "productImage": "http://a.jpg"},
        {"productName": "B", "productUrl": "http://b", "productImage": "http://b.jpg"},
    ]


def test_load_products_parses_lines_skipping_comments_bad_lines_and_dup_urls(tmp_path):
    path = tmp_path / "products.txt"
    path.write_text(
        "# 주석\n"
        "\n"
        "케이스 | http://a | http://a.jpg\n"
        "링크 없는 줄\n"
        "이미지 없음 | http://b\n"
        "중복 | http://a\n",
        encoding="utf-8",
    )

    result = main._load_products(str(path))

    assert result == [
        {"productName": "케이스", "productUrl": "http://a", "productImage": "http://a.jpg"},
        {"productName": "이미지 없음", "productUrl": "http://b", "productImage": ""},
    ]


def test_real_products_file_parses():
    assert main._load_products(main.PRODUCTS_PATH)


def test_pick_product_skips_posted():
    posted = {main.hash_link("http://a")}

    assert main._pick_product(_products(), posted)["productUrl"] == "http://b"
    assert main._pick_product(_products(), posted | {main.hash_link("http://b")}) is None


PATCHED = [
    "save_posted_ids", "upload_video", "refresh_access_token", "build_description",
    "assemble_video", "synthesize", "save_generated_image", "generate_image",
    "download_image", "write_script", "load_posted_ids", "_load_products", "load_settings",
    "pick_bgm",
]


def _patch_pipeline(func):
    for name in PATCHED:
        func = patch(f"main.{name}")(func)
    return func


def _setup(m, sentences):
    settings = MagicMock()
    settings.telegram_channel_url = "https://t.me/x"
    m["load_settings"].return_value = settings
    m["_load_products"].return_value = _products()
    m["load_posted_ids"].return_value = set()
    m["write_script"].return_value = {
        "title": "제목",
        "sentences": sentences,
        "keywords": ["케이스"],
        "image_prompts": [f"prompt{i}" for i in range(1, len(sentences) + 1)],
    }
    m["save_generated_image"].side_effect = lambda d, name, data: f"work/{name}"
    m["synthesize"].return_value = [f"work/{i}.mp3" for i in range(len(sentences))]
    m["assemble_video"].return_value = "work/final.mp4"
    m["build_description"].return_value = "설명"
    m["refresh_access_token"].return_value = "token"
    m["upload_video"].return_value = "https://youtu.be/abc123"
    m["pick_bgm"].return_value = ("bgm/song.mp3", "🎵 Music: song")
    return settings


def _mocks(args):
    return dict(zip(PATCHED, args))  # 먼저 적용된(안쪽) patch가 첫 인자


@_patch_pipeline
def test_run_uses_product_photo_first_then_ai_images(*args):
    m = _mocks(args)
    settings = _setup(m, ["문장1", "문장2", "문장3"])
    m["download_image"].return_value = JPG
    m["generate_image"].side_effect = [PNG, b"not an image"]

    result = main.run()

    assert result == "https://youtu.be/abc123"
    m["write_script"].assert_called_once_with(settings, _products()[0])
    m["download_image"].assert_called_once_with("http://a.jpg")
    assert [c.args[1] for c in m["generate_image"].call_args_list] == ["prompt2", "prompt3"]
    # 3번째 AI 이미지 실패 → 상품 사진 재사용
    assert m["assemble_video"].call_args[0][2] == [
        "work/image_1.png", "work/image_2.png", "work/image_3.png"
    ]
    assert m["save_generated_image"].call_args_list[2].args[2] == JPG
    m["build_description"].assert_called_once_with(
        "문장1 문장2", _products()[0], "https://t.me/x", ["케이스"]
    )
    assert m["upload_video"].call_args[0][3] == "[광고] 제목"
    assert m["upload_video"].call_args[0][4] == "설명\n\n🎵 Music: song"
    assert m["assemble_video"].call_args.kwargs["bgm_path"] == "bgm/song.mp3"
    assert m["upload_video"].call_args.kwargs["tags"] == ["쇼츠", "쿠팡", "쿠팡추천템", "케이스"]
    m["save_posted_ids"].assert_called_once()
    assert main.hash_link("http://a") in m["save_posted_ids"].call_args[0][1]


@_patch_pipeline
def test_run_falls_back_to_ai_image_when_product_photo_fails(*args):
    m = _mocks(args)
    _setup(m, ["문장1"])
    m["download_image"].return_value = b"<html>error</html>"
    m["generate_image"].return_value = PNG

    main.run()

    assert m["generate_image"].call_args.args[1] == "prompt1"
    assert m["assemble_video"].call_args[0][2] == ["work/image_1.png"]


@_patch_pipeline
def test_run_returns_none_when_all_products_posted(*args):
    m = _mocks(args)
    _setup(m, ["문장1"])
    m["load_posted_ids"].return_value = {main.hash_link(p["productUrl"]) for p in _products()}

    assert main.run() is None
    m["write_script"].assert_not_called()


@_patch_pipeline
def test_run_does_not_save_posted_ids_when_upload_fails(*args):
    m = _mocks(args)
    _setup(m, ["문장1"])
    m["download_image"].return_value = None
    m["generate_image"].return_value = None
    m["upload_video"].side_effect = RuntimeError("quota exceeded")

    with pytest.raises(RuntimeError):
        main.run()

    m["save_posted_ids"].assert_not_called()


@_patch_pipeline
def test_run_uses_color_background_when_photo_and_ai_both_fail(*args):
    m = _mocks(args)
    _setup(m, ["문장1", "문장2"])
    m["download_image"].return_value = None
    m["generate_image"].return_value = None

    main.run()

    assert m["assemble_video"].call_args[0][2] == [None, None]
