COUPANG_DISCLOSURE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


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
    tags = ["쿠팡", "추천템", "쇼츠", *keywords]
    lines.append(" ".join(f"#{k.replace(' ', '')}" for k in tags))

    return "\n".join(lines)
