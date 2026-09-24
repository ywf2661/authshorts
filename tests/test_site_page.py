from site_page import build_page


def test_build_page_lists_newest_first_with_escaped_links():
    records = [
        {"number": 1, "topic": "방한템", "url": "https://youtu.be/a",
         "products": [{"name": "텐트", "link": "http://c/1"}]},
        {"number": 2, "topic": "<주방템>", "url": "https://youtu.be/b",
         "products": [{"name": "도마", "link": "http://c/2?a=1&b=2"}, {"name": "수세미", "link": "http://c/3"}]},
    ]

    page = build_page(records)

    assert page.index("쿠팡 파트너스") < page.index(">#2 ") < page.index(">#1 ")
    assert "&lt;주방템&gt;" in page
    assert 'href="http://c/2?a=1&amp;b=2"' in page
    assert "2위 · 수세미" in page
    assert 'id="2"' in page


def test_build_page_without_records():
    assert "아직 영상이 없어요" in build_page([])
