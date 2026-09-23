COUPANG_DISCLOSURE = "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def build_description(
    script_summary: str, products: list[dict], telegram_url: str, keywords: list[str]
) -> str:
    """쇼츠 설명란 텍스트를 조립한다. 관련상품이 없으면 그 섹션은 생략한다."""
    lines = [script_summary, ""]

    if products:
        lines.append("🔗 관련 상품")
        lines.append(COUPANG_DISCLOSURE)
        for p in products:
            lines.append(f"{p['productName']}: {p['productUrl']}")
        lines.append("")

    lines.append(f"📢 AI 뉴스 텔레그램: {telegram_url}")

    lines.append("")
    tags = ["AI", "쇼츠", *keywords]
    lines.append(" ".join(f"#{k.replace(' ', '')}" for k in tags))

    return "\n".join(lines)
