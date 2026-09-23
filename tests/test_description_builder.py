from description_builder import build_description


def test_build_description_includes_products_and_telegram_link():
    result = build_description(
        "오늘의 AI 소식 요약",
        [{"productName": "노트북 A", "productUrl": "http://x"}],
        "https://t.me/channel",
        ["노트북"],
    )

    assert "노트북 A: http://x" in result
    assert "쿠팡 파트너스 활동의 일환" in result
    assert "https://t.me/channel" in result
    assert "#AI" in result
    assert "#노트북" in result


def test_build_description_omits_product_section_when_empty():
    result = build_description("오늘의 AI 소식 요약", [], "https://t.me/channel", [])

    assert "관련 상품" not in result
    assert "https://t.me/channel" in result


def test_build_description_always_includes_fixed_hashtags_even_without_keywords():
    result = build_description("오늘의 AI 소식 요약", [], "https://t.me/channel", [])

    assert "#AI" in result
    assert "#쇼츠" in result
