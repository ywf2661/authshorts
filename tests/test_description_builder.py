from description_builder import build_description

PRODUCT = {"productName": "투명 케이스", "productUrl": "http://x"}


def test_build_description_puts_disclosure_first_then_product_link():
    result = build_description("요약", PRODUCT, "https://t.me/channel", ["휴대폰 케이스"])
    lines = result.split("\n")

    assert "쿠팡 파트너스 활동의 일환" in lines[0]
    assert "투명 케이스" in lines[2]
    assert lines[3] == "http://x"
    assert "https://t.me/channel" in result
    assert lines[-1] == "#쇼츠 #쿠팡 #쿠팡추천템 #휴대폰케이스"


def test_hashtags_strip_symbols_dedupe_and_cap_at_ten():
    from description_builder import hashtags

    tags = hashtags(["#자취템", "살림 꿀템", "쿠팡", ""] + [f"태그{i}" for i in range(20)])

    assert tags[:5] == ["쇼츠", "쿠팡", "쿠팡추천템", "자취템", "살림꿀템"]
    assert len(tags) == 10


def test_build_top_description_lists_ranks_with_profile_number():
    from description_builder import build_top_description

    products = [{"productName": "난방텐트", "productUrl": "http://a"},
                {"productName": "담요", "productUrl": "http://b"}]
    result = build_top_description(products, 7, ["방한템"])
    lines = result.split("\n")

    assert "쿠팡 파트너스 활동의 일환" in lines[0]
    assert "프로필 링크 #7" in lines[2]
    assert lines[4:6] == ["1위 난방텐트", "http://a"]
    assert lines[7:9] == ["2위 담요", "http://b"]
    assert "#방한템" in lines[-1]
