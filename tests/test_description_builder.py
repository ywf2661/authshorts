from description_builder import build_description

PRODUCT = {"productName": "투명 케이스", "productUrl": "http://x"}


def test_build_description_puts_disclosure_first_then_product_link():
    result = build_description("요약", PRODUCT, "https://t.me/channel", ["휴대폰 케이스"])
    lines = result.split("\n")

    assert "쿠팡 파트너스 활동의 일환" in lines[0]
    assert "투명 케이스" in lines[2]
    assert lines[3] == "http://x"
    assert "https://t.me/channel" in result
    assert lines[-1] == "#쿠팡 #추천템 #쇼츠 #휴대폰케이스"
