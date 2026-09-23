def build_description(
    script_summary: str, products: list[dict], telegram_url: str, keywords: list[str]
) -> str:
    """쇼츠 설명란 텍스트를 조립한다. 관련상품이 없으면 그 섹션은 생략한다."""
    lines = [script_summary, ""]

    if products:
        lines.append("🔗 관련 상품")
        for p in products:
            lines.append(f"{p['productName']}: {p['productUrl']}")
        lines.append("")

    lines.append(f"📢 AI 뉴스 텔레그램: {telegram_url}")

    lines.append("")
    tags = ["AI", "쇼츠", *keywords]
    lines.append(" ".join(f"#{k.replace(' ', '')}" for k in tags))

    return "\n".join(lines)
