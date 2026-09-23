import json

import requests

from config import Settings

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

MIN_SENTENCES = 1
MAX_SENTENCES = 8

PROMPT_TEMPLATE = """다음 쿠팡 상품을 소개하는 유튜브 쇼츠를 만든다.

상품명: {product_name}

이 상품을 "요즘 잇템"으로 소개하는 30~45초 분량(문장 4~6개)의 한국어 나레이션 대본을 작성하라.
첫 문장은 시청자가 스크롤을 멈추게 하는 후킹 문장(어떤 불편/상황을 해결하는지)으로 시작하고,
마지막 문장은 "설명란 링크에서 확인해보세요" 같은 행동 유도로 끝내라.
상품명에 드러나지 않은 구체적인 스펙·수치·효능은 지어내지 마라. 가격은 바뀔 수 있으니 금액을 말하지 마라.
각 문장은 그 자체로 한 화면(이미지 1장)에 어울리는 길이로 끊어라.
각 문장에 어울리는 삽화를 묘사하는 영문 이미지 생성 프롬프트를 sentences와 같은 순서·개수로
image_prompts에 넣어라 (사진이 아닌 삽화/일러스트 스타일로, 상품을 쓰는 상황을 묘사할 것 — 실존 인물·브랜드 로고를
특정하지 말 것).
해시태그로 쓸 상품 카테고리 키워드를 1~2개 뽑아라 (예: "휴대폰케이스", "노트북").

다음 JSON 형식으로만 응답하라. 다른 텍스트는 포함하지 마라:
{{"title": "쇼츠 제목", "sentences": ["문장1", "문장2"], "keywords": ["키워드1"], "image_prompts": ["illustration prompt 1", "illustration prompt 2"]}}
"""


def _validate_script_shape(sentences, image_prompts) -> None:
    if not isinstance(sentences, list) or not sentences:
        raise ValueError(f"sentences는 비어있지 않은 리스트여야 함: {sentences!r}")
    if not (MIN_SENTENCES <= len(sentences) <= MAX_SENTENCES):
        raise ValueError(
            f"sentences 개수가 허용 범위(1~{MAX_SENTENCES})를 벗어남: {len(sentences)}개"
        )
    if not all(isinstance(s, str) and s for s in sentences):
        raise ValueError(f"sentences에는 비어있지 않은 문자열만 허용됨: {sentences!r}")

    if not isinstance(image_prompts, list) or len(image_prompts) != len(sentences):
        raise ValueError(
            "image_prompts 개수가 sentences와 일치하지 않음: "
            f"{len(image_prompts) if isinstance(image_prompts, list) else image_prompts!r}"
            f" != {len(sentences)}"
        )
    if not all(isinstance(p, str) and p for p in image_prompts):
        raise ValueError(f"image_prompts에는 비어있지 않은 문자열만 허용됨: {image_prompts!r}")


def write_script(settings: Settings, product: dict) -> dict:
    """쿠팡 상품 1개를 소개하는 쇼츠 대본을 작성한다."""
    prompt = PROMPT_TEMPLATE.format(product_name=product["productName"])
    response = requests.post(
        API_URL,
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 2000,
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "{"},
            ],
        },
        timeout=60,
    )
    response.raise_for_status()
    response_body = response.json()
    try:
        text = response_body["content"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Claude 응답 구조 오류: {response_body!r}") from e
    try:
        result = json.loads("{" + text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답이 JSON이 아님: {text!r}") from e

    required = ("title", "sentences", "image_prompts")
    if any(key not in result for key in required):
        raise ValueError(f"Claude 응답에 필수 필드 누락: {result!r}")

    _validate_script_shape(result["sentences"], result["image_prompts"])

    return {
        "title": result["title"],
        "sentences": result["sentences"],
        "keywords": result.get("keywords", []),
        "image_prompts": result["image_prompts"],
    }
