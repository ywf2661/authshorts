import base64
import json
import re

import anthropic

from config import Settings

MODEL = "claude-sonnet-5"

BEAT_KINDS = ["hook", "item", "reveal", "outro"]
MAX_BEAT_CHARS = 30  # 프롬프트는 25자 — 조금 넘는 건 봐준다
TOTAL_CHARS = (120, 190)  # 공백 제외. 프롬프트는 140~170자(+20% 속도로 약 22~26초)

FIRST_PERSON = re.compile(r"써봤|써보니|써 보니|제가|저는|내돈내산|직접 써")
# 근거가 필요한 주장 — 해당 상품 '포인트'에 같은 말이 있어야 한다.
CLAIMS = re.compile(r"품절|매출|판매 ?1위|직원|극찬|재구매율|전기료|절감|화재|안전 ?인증|\d+(?:\.\d+)? ?%")
PRICE = re.compile(r"\d[\d,.]*\s*[만천]?\s*원")

HOOK_RULES = {
    "result": (
        "결과·손실형으로 시작한다 — 예: '안 쓰면 고생하는', '늦게 살수록 후회하는', '주변엔 말하지 마세요', "
        "계절 문제를 해결해주는 식. hook_lines도 같은 결로."
    ),
    "quiz": "퀴즈형 — '1위 맞혀보세요'처럼 1위를 맞혀보라고 한다. 1위 상품명은 말하지 않는다. hook_lines도 같은 결로.",
}

TOP_PROMPT = """위 이미지는 상품별 첫 사진이다 (상품 번호 순서).
쿠팡 상품 {n}개로 "{topic}" TOP{n} 유튜브 쇼츠 대본을 쓴다.

상품 (번호 0 = 1위, 번호 순서가 곧 순위):
{product_lines}

규칙:
- 영상은 {n}위 → 1위 순서로 공개한다. 대본은 장면(beat) 리스트다. 장면 1개 = 한 호흡, 25자 이내.
- 장면 종류: hook(첫 1~2장면) → item({n}위~2위, 순위마다 1~3장면) → reveal(1위, 2~4장면. 첫 장면은 "대망의 1위는 ~" 식) → outro(마지막 1장면, 댓글을 부르는 질문).
- product = 그 장면이 다루는 상품 번호. hook·outro는 0. rank = item·reveal은 그 상품 순위(번호+1), hook·outro는 0.
- 전체 대사는 공백 빼고 140~170자. {n}위 구간이 가장 짧고 1위 구간이 가장 길다.
- 훅: 첫 장면을 상품명으로 시작하지 않는다. {hook_rule}
- 장면마다 핵심 단어 하나를 *별표*로 감싼다 (화면에서 노랑 강조, 없어도 됨).
- 사실은 각 상품의 '포인트'와 사진에 보이는 것에서만 가져온다. 포인트에 없는 판매량·품절·수치·%·인증·후기·절감 효과는 지어내지 않는다.
- 직접 써본 것처럼 말하지 않는다 (써봤·제가·저는·내돈내산 금지). 가격·금액은 말하지 않는다.
- hook_lines: 첫 화면 가운데 큰 글씨 2~3줄 (줄당 7자 이내).
- labels: 화면에 띄울 상품별 짧은 이름 (8자 이내), 상품 번호 순서대로 {n}개.
- title: 유튜브 제목 (40자 이내, 주제와 TOP{n}이 드러나게).
- keywords: 해시태그 5~7개 — 상품 종류, 쓰는 상황, 타깃 시청자를 섞은 실제 검색어 (한국어, #·띄어쓰기 없이).
"""

_STR_LIST = {"type": "array", "items": {"type": "string"}}
TOP_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook_lines": _STR_LIST,
        "labels": _STR_LIST,
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": BEAT_KINDS},
                    "product": {"type": "integer"},
                    "rank": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["kind", "product", "rank", "text"],
                "additionalProperties": False,
            },
        },
        "keywords": _STR_LIST,
    },
    "required": ["title", "hook_lines", "labels", "beats", "keywords"],
    "additionalProperties": False,
}


class ScriptRejected(Exception):
    """재요청까지 검사에 실패한 대본 — 그날은 업로드하지 않는다."""


def _ask_claude(settings: Settings, content, schema: dict) -> dict:
    """Claude에 스키마에 맞는 JSON 응답을 요청해 dict로 반환한다."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    if response.stop_reason == "refusal":
        raise ValueError(f"Claude가 응답을 거절함: {response.stop_details}")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude 응답이 JSON이 아님 (stop_reason={response.stop_reason}): {text!r}") from e


def _media_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _image_block(data: bytes) -> dict | None:
    media_type = _media_type(data)
    if media_type is None:
        return None
    return {"type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}}


def plain(text: str) -> str:
    """화면 강조 표시(*)를 뺀 대사."""
    return " ".join(text.replace("*", "").split())


def check_top_script(script: dict, products: list[dict], topic: str) -> list[str]:
    """사진 TOP 대본 검사 — 문제 목록 (비었으면 통과)."""
    n = len(products)
    problems = []
    beats = script.get("beats") or []
    if len(script.get("labels", [])) != n:
        problems.append(f"labels는 상품 수와 같은 {n}개여야 함")
    if not script.get("hook_lines"):
        problems.append("hook_lines가 비었음")
    if not beats or beats[0].get("kind") != "hook" or beats[-1].get("kind") != "outro":
        problems.append("첫 장면은 hook, 마지막 장면은 outro여야 함")
    if not any(b.get("kind") == "reveal" for b in beats):
        problems.append("reveal(1위) 장면이 없음")
    ranks = [b.get("rank") for b in beats if b.get("kind") in ("item", "reveal")]
    if ranks != sorted(ranks, reverse=True):
        problems.append(f"순위는 {n}위 → 1위 순서여야 함: {ranks}")

    total = 0
    for i, beat in enumerate(beats):
        text = plain(beat.get("text", ""))
        product = beat.get("product")
        if not text:
            problems.append(f"장면 {i}: 대사가 비었음")
            continue
        total += len(text.replace(" ", ""))
        if len(text) > MAX_BEAT_CHARS:
            problems.append(f"장면 {i}: 너무 김 ({len(text)}자) — 25자 이내로 나눌 것")
        if not isinstance(product, int) or not 0 <= product < n:
            problems.append(f"장면 {i}: product 번호가 범위 밖 ({product})")
            continue
        if beat.get("kind") == "reveal" and product != 0:
            problems.append(f"장면 {i}: reveal은 1위(0번) 상품이어야 함")
        if beat.get("kind") in ("item", "reveal") and beat.get("rank") != product + 1:
            problems.append(f"장면 {i}: {product}번 상품의 순위는 {product + 1}위")
        if FIRST_PERSON.search(text):
            problems.append(f"장면 {i}: 직접 써본 것 같은 1인칭 후기 표현 금지 — '{text}'")
        point = products[product]["point"]
        for claim in CLAIMS.findall(text):
            if claim.replace(" ", "") not in point.replace(" ", ""):
                problems.append(f"장면 {i}: '{claim}'은 상품 포인트에 근거가 없음 — '{text}'")
        for price in PRICE.findall(text):
            if price.replace(" ", "") not in topic.replace(" ", ""):
                problems.append(f"장면 {i}: 가격·금액 언급 금지 — '{price}'")

    if beats:
        first = plain(beats[0].get("text", ""))
        names = [p["productName"] for p in products] + list(script.get("labels", []))
        if any(name and first.startswith(name) for name in names):
            problems.append("훅 첫 장면을 상품명으로 시작하지 말 것")
    if not TOTAL_CHARS[0] <= total <= TOTAL_CHARS[1]:
        problems.append(f"전체 대사 {total}자 — 공백 빼고 140~170자로 맞출 것")
    return problems


def write_top_script(
    settings: Settings, topic: str, products: list[dict], first_photos: list[bytes], hook: str
) -> dict:
    """묶음 상품으로 TOP N 대본을 쓴다. 검사에 걸리면 사유를 붙여 1회 재요청, 또 걸리면 ScriptRejected."""
    content = []
    for i, photo in enumerate(first_photos):
        block = _image_block(photo)
        if block:
            content += [{"type": "text", "text": f"상품 {i} 사진"}, block]
    product_lines = "\n".join(
        f"{i}. ({i + 1}위) {p['productName']} — 포인트: {p['point']}" for i, p in enumerate(products)
    )
    prompt = TOP_PROMPT.format(
        n=len(products), topic=topic, product_lines=product_lines, hook_rule=HOOK_RULES[hook]
    )

    problems = []
    for _ in range(2):
        extra = ""
        if problems:
            extra = "\n\n직전 대본이 아래 검사에 걸렸다. 고쳐서 다시 써라:\n- " + "\n- ".join(problems)
        script = _ask_claude(settings, content + [{"type": "text", "text": prompt + extra}], TOP_SCHEMA)
        problems = check_top_script(script, products, topic)
        if not problems:
            return script
        print("대본 검사 실패:", problems)
    raise ScriptRejected("; ".join(problems))


CLIP_PROMPT = """위 이미지들은 쿠팡 상품 "{product_name}"의 실제 사용 영상(총 {duration:.0f}초)에서
균등 간격으로 뽑은 프레임이고, 각 이미지 앞의 t=숫자는 그 프레임의 영상 내 시각(초)이다.

이 영상으로 "요즘 잇템"을 소개하는 20~30초 분량의 한국어 나레이션 쇼츠를 만든다.
대본은 장면(segment) 4~8개이고, 장면 1개 = 한 호흡(25자 이내)이다.
장면마다 대사와 가장 잘 어울리는 화면의 시작 시각(start, 초)을 위 t 값 중에서 골라라.
흔들리거나 흐리거나 아무것도 안 보이는 프레임은 고르지 마라. 가능하면 서로 다른 장면을 골라라.
첫 장면은 스크롤을 멈추게 하는 후킹 대사(상품명으로 시작하지 말 것), 마지막 장면은 "프로필 링크에서 확인해보세요" 같은 행동 유도.
장면마다 핵심 단어 하나를 *별표*로 감싼다 (화면에서 노랑 강조, 없어도 됨).
화면에 보이는 것과 상품명에 드러난 것 이외의 스펙·수치·효능은 지어내지 마라. 가격은 말하지 마라.
hook_lines: 첫 화면 가운데 큰 글씨 2~3줄 (줄당 7자 이내, 예: ["N통째 쓴", "쿠팡필수템"]).
keywords: 해시태그 5~7개 — 상품 종류, 쓰는 상황, 타깃 시청자를 섞은 실제 검색어 (한국어, #·띄어쓰기 없이).
"""

CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook_lines": _STR_LIST,
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"start": {"type": "number"}, "text": {"type": "string"}},
                "required": ["start", "text"],
                "additionalProperties": False,
            },
        },
        "keywords": _STR_LIST,
    },
    "required": ["title", "hook_lines", "segments", "keywords"],
    "additionalProperties": False,
}


def write_clip_script(
    settings: Settings, product: dict, frames: list[tuple[float, bytes]], duration: float
) -> dict:
    """사용 영상 프레임을 보고 장면별 나레이션 대본을 쓴다 (실제 사용 영상이라 1인칭 허용)."""
    content = []
    for t, jpeg in frames:
        content += [{"type": "text", "text": f"t={t}"}, _image_block(jpeg)]
    content.append({"type": "text", "text": CLIP_PROMPT.format(
        product_name=product["productName"], duration=duration)})
    result = _ask_claude(settings, content, CLIP_SCHEMA)

    segments = result["segments"]
    if not 1 <= len(segments) <= 10:
        raise ValueError(f"장면 개수가 허용 범위를 벗어남: {len(segments)}개")
    for seg in segments:
        if not plain(seg["text"]):
            raise ValueError(f"빈 대사: {segments!r}")
        if not 0 <= seg["start"] < duration:
            raise ValueError(f"start가 영상 범위를 벗어남: {seg['start']!r} (영상 {duration}초)")
    return result
