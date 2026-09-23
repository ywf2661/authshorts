import json

CURATED_PRODUCTS_PATH = "curated_products.json"
DEFAULT_CATEGORY = "기본"


def _load_catalog(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def search_products(keyword: str, limit: int = 3) -> list[dict]:
    """키워드에 맞는 수동 큐레이션 쿠팡 상품을 반환한다.

    매칭되는 카테고리가 없으면 '기본' 카테고리, 그마저 없으면 빈 리스트.
    """
    catalog = _load_catalog(CURATED_PRODUCTS_PATH)
    keyword_lower = keyword.lower()
    # ponytail: 단순 부분일치 — 동의어/형태소 매칭은 안 함. 매칭률이 낮으면
    # 카테고리 키에 동의어를 추가하거나 별도 동의어 맵을 두는 식으로 확장.
    for category, products in catalog.items():
        if category == DEFAULT_CATEGORY:
            continue
        category_lower = category.lower()
        if category_lower in keyword_lower or keyword_lower in category_lower:
            return products[:limit]
    return catalog.get(DEFAULT_CATEGORY, [])[:limit]
