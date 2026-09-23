COUPANG_DISCLOSURE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
BASE_HASHTAGS = ["쇼츠", "쿠팡", "쿠팡추천템"]
# 유튜브는 해시태그가 15개를 넘으면 전부 무시한다 — 여유 있게 10개로 자른다.
MAX_HASHTAGS = 10


def hashtags(keywords: list[str]) -> list[str]:
    """기본 태그 + Claude 태그를 '#'·공백 없이, 중복 없이 최대 10개로."""
    tags = []
    for k in [*BASE_HASHTAGS, *keywords]:
        tag = str(k).replace("#", "").replace(" ", "").strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags[:MAX_HASHTAGS]


def build_description(
    script_summary: str, product: dict, telegram_url: str, keywords: list[str]
) -> str:
    """쇼츠 설명란 텍스트를 조립한다. 수수료 고지와 상품 링크를 맨 위에 둔다."""
    lines = [
        COUPANG_DISCLOSURE,
        "",
        f"🛒 {product['productName']}",
        product["productUrl"],
        "",
        script_summary,
        "",
        f"📢 텔레그램: {telegram_url}",
        "",
    ]
    lines.append(" ".join(f"#{tag}" for tag in hashtags(keywords)))

    return "\n".join(lines)
