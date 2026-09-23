import base64
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
해시태그 5~7개를 keywords에 넣어라 — 상품 종류, 쓰는 상황, 타깃 시청자를 섞어서 사람들이 실제로 검색할 만한 한국어로 (예: "아이폰케이스", "자취템", "살림꿀템", "직장인선물"). # 기호와 띄어쓰기 없이.
영상 첫 화면 가운데에 크게 박을 후킹 제목을 2~3줄(줄당 7자 이내)로 cover_lines에 넣어라
(예: ["N통째 쓴", "쿠팡필수템", "TOP 1"] / ["자취생", "필수템"]).
가장 임팩트 있는 문장 1~2개(첫 문장 제외)를 골라 그 인덱스(0부터)를 emphasis에 넣어라 — 확대·집중선 효과가 들어간다.

다음 JSON 형식으로만 응답하라. 다른 텍스트는 포함하지 마라:
{{"title": "쇼츠 제목", "cover_lines": ["줄1", "줄2"], "emphasis": [2], "sentences": ["문장1", "문장2"], "keywords": ["태그1", "태그2"], "image_prompts": ["illustration prompt 1", "illustration prompt 2"]}}
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


def _cover_lines(result: dict) -> list[str] | None:
    """큰 제목 줄. 형식이 이상하면 제목 없이 진행한다 (영상 전체를 실패시킬 이유는 아님)."""
    lines = result.get("cover_lines")
    if isinstance(lines, list) and 1 <= len(lines) <= 3 and all(isinstance(x, str) and x.strip() for x in lines):
        return [x.strip() for x in lines]
    return None


def _emphasis(result: dict, sentence_count: int) -> list[int]:
    """강조 문장 인덱스. 첫 문장(제목 장면)과 범위 밖 값은 버린다."""
    raw = result.get("emphasis")
    if not isinstance(raw, list):
        return []
    return sorted({i for i in raw if isinstance(i, int) and 0 < i < sentence_count})[:2]


def _ask_claude(settings: Settings, content) -> dict:
    """Claude에 JSON 응답을 요청해 dict로 파싱한다."""
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
                {"role": "user", "content": content},
                {"role": "assistant", "content": "{"},
            ],
        },
        timeout=120,
    )
    response.raise_for_status()
    response_body = response.json()
    try:
        text = response_body["content"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ValueError(f"Claude 응답 구조 오류: {response_body!r}") from e
    try:
        return json.loads("{" + text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답이 JSON이 아님: {text!r}") from e


def write_script(settings: Settings, product: dict) -> dict:
    """쿠팡 상품 1개를 소개하는 쇼츠 대본을 작성한다."""
    result = _ask_claude(settings, PROMPT_TEMPLATE.format(product_name=product["productName"]))

    required = ("title", "sentences", "image_prompts")
    if any(key not in result for key in required):
        raise ValueError(f"Claude 응답에 필수 필드 누락: {result!r}")

    _validate_script_shape(result["sentences"], result["image_prompts"])

    return {
        "title": result["title"],
        "cover_lines": _cover_lines(result),
        "emphasis": _emphasis(result, len(result["sentences"])),
        "sentences": result["sentences"],
        "keywords": result.get("keywords", []),
        "image_prompts": result["image_prompts"],
    }


CLIP_PROMPT_TEMPLATE = """위 이미지들은 쿠팡 상품 "{product_name}"의 실제 사용 영상(총 {duration:.0f}초)에서
균등 간격으로 뽑은 프레임이고, 각 이미지 앞의 t=숫자는 그 프레임의 영상 내 시각(초)이다.

이 영상으로 "요즘 잇템"을 소개하는 30~45초 분량(문장 4~6개)의 한국어 나레이션 쇼츠를 만든다.
각 문장마다 그 문장과 가장 잘 어울리는 장면의 시작 시각(start, 초)을 위 t 값 중에서 골라라.
흔들리거나 흐리거나 아무것도 안 보이는 프레임은 고르지 마라. 가능하면 서로 다른 장면을 골라라.
첫 문장은 스크롤을 멈추게 하는 후킹 문장으로, 마지막 문장은 "설명란 링크에서 확인해보세요" 같은 행동 유도로 끝내라.
화면에 보이는 것과 상품명에 드러난 것 이외의 스펙·수치·효능은 지어내지 마라. 가격은 말하지 마라.
해시태그 5~7개를 keywords에 넣어라 — 상품 종류, 쓰는 상황, 타깃 시청자를 섞어서 사람들이 실제로 검색할 만한 한국어로 (예: "아이폰케이스", "자취템", "살림꿀템", "직장인선물"). # 기호와 띄어쓰기 없이.
영상 첫 화면 가운데에 크게 박을 후킹 제목을 2~3줄(줄당 7자 이내)로 cover_lines에 넣어라
(예: ["N통째 쓴", "쿠팡필수템", "TOP 1"] / ["자취생", "필수템"]).
가장 임팩트 있는 문장 1~2개(첫 문장 제외)를 골라 그 인덱스(0부터)를 emphasis에 넣어라 — 확대·집중선 효과가 들어간다.

다음 JSON 형식으로만 응답하라:
{{"title": "쇼츠 제목", "cover_lines": ["줄1", "줄2"], "emphasis": [2], "segments": [{{"start": 0, "sentence": "문장1"}}], "keywords": ["태그1", "태그2"]}}
"""


def write_clip_script(
    settings: Settings, product: dict, frames: list[tuple[float, bytes]], duration: float
) -> dict:
    """사용 영상 프레임을 보고 장면별 나레이션 대본을 작성한다."""
    content = []
    for t, jpeg in frames:
        content.append({"type": "text", "text": f"t={t}"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.b64encode(jpeg).decode()},
        })
    content.append({
        "type": "text",
        "text": CLIP_PROMPT_TEMPLATE.format(product_name=product["productName"], duration=duration),
    })
    result = _ask_claude(settings, content)

    segments = result.get("segments")
    if "title" not in result or not isinstance(segments, list):
        raise ValueError(f"Claude 응답에 필수 필드 누락: {result!r}")
    sentences = [seg.get("sentence") for seg in segments if isinstance(seg, dict)]
    _validate_script_shape(sentences, sentences)  # 이미지 프롬프트 대신 문장 자체로 개수 검증
    starts = []
    for seg in segments:
        start = seg.get("start")
        if not isinstance(start, (int, float)) or not (0 <= start < duration):
            raise ValueError(f"start가 영상 범위를 벗어남: {start!r} (영상 {duration}초)")
        starts.append(float(start))

    return {
        "title": result["title"],
        "cover_lines": _cover_lines(result),
        "emphasis": _emphasis(result, len(sentences)),
        "sentences": sentences,
        "starts": starts,
        "keywords": result.get("keywords", []),
    }
