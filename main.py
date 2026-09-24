"""사진 TOP3 쇼츠봇: products.txt의 [주제] 묶음 하나로 3위→1위 공개 쇼츠를 만들어 올린다."""
import datetime
import json
import os
import random
import re

import requests

from config import Settings, load_settings
from dedup import hash_link, load_posted_ids, save_posted_ids
from description_builder import build_top_description, hashtags
from script_writer import ScriptRejected, write_top_script
from tts import synthesize, timeline
from video_assembler import (
    BADGE_Y, CTA_Y, HEADER_Y, POP, YELLOW, ad_events, caption_events, clean_text, event,
    pick_bgm, probe_duration, render, sfx_path, title_events, write_ass,
)
from youtube_api import refresh_access_token, upload_video

ROOT = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_PATH = os.path.join(ROOT, "products.txt")
POSTED_IDS_PATH = os.path.join(ROOT, "shorts_posted_ids.json")
POSTED_VIDEOS_PATH = os.path.join(ROOT, "posted_videos.json")
WORK_DIR = "work"
AD_PREFIX = "[광고] "  # 공정위 추천·보증 심사지침: 영상 광고는 제목에 경제적 이해관계 표시
MIN_PRODUCTS, MAX_PRODUCTS = 2, 5
MAX_PHOTOS = 3
LOW_STOCK = 2  # 업로드 후 남은 묶음이 이 이하이면 알림
TAIL = 0.5  # 나레이션이 끝난 뒤 여유 (초)

# 순위별 밝은 배경 (1위, 2위, 3위, ...) — 영상마다 하나를 고른다.
PALETTES = [
    ["#FFD93D", "#6BCB77", "#4D96FF", "#FF8FAB", "#B8F2E6"],
    ["#FF9F1C", "#2EC4B6", "#A0C4FF", "#FFBF69", "#CDB4DB"],
    ["#F9C74F", "#90BE6D", "#F8961E", "#43AA8B", "#F28482"],
    ["#FFADAD", "#9BF6FF", "#CAFFBF", "#FDFFB6", "#BDB2FF"],
]


def parse_product_line(line: str) -> dict | None:
    """'상품명 | 링크 | 이미지 주소들(공백 구분) | 포인트' 한 줄을 상품 dict로. 형식이 틀리면 None.

    사용 영상 봇 캡션처럼 '상품명 | 링크'만 있어도 된다 (이미지·포인트는 빈 값).
    """
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1].startswith("http"):
        return None
    images = parts[2].split()[:MAX_PHOTOS] if len(parts) > 2 else []
    point = re.sub(r"^포인트\s*:\s*", "", parts[3]) if len(parts) > 3 else ""
    return {"productName": parts[0], "productUrl": parts[1], "images": images, "point": point}


def load_bundles(path: str) -> list[dict]:
    """'[주제]' 줄로 시작하는 묶음들을 파일 순서대로 읽는다. 묶음 안 적은 순서 = 1위 → N위."""
    bundles, current = [], None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            topic = re.fullmatch(r"\[(.+)\]", line)
            if topic:
                current = {"topic": topic.group(1).strip(), "products": []}
                bundles.append(current)
                continue
            product = parse_product_line(line)
            if product is None:
                print(f"형식이 잘못된 줄은 건너뜀: {line}")
            elif current is None:
                print(f"[주제] 묶음 밖의 상품 줄은 무시: {line}")
            else:
                current["products"].append(product)
    valid = []
    for bundle in bundles:
        if MIN_PRODUCTS <= len(bundle["products"]) <= MAX_PRODUCTS:
            valid.append(bundle)
        else:
            print(f"[{bundle['topic']}] 상품이 {len(bundle['products'])}개 — {MIN_PRODUCTS}~{MAX_PRODUCTS}개여야 해서 건너뜀")
    return valid


def bundle_key(bundle: dict) -> str:
    return hash_link("".join(p["productUrl"] for p in bundle["products"]))


def original_image_url(url: str) -> str:
    """쿠팡 썸네일 주소를 원본(800~1000px) 주소로. 쿠팡 썸네일이 아니면 그대로."""
    m = re.match(r"https?://thumbnail\d*\.coupangcdn\.com/thumbnails/remote/[^/]+/(image/.+)", url)
    return f"https://image1.coupangcdn.com/{m.group(1)}" if m else url


def _is_image(data: bytes | None) -> bool:
    # 쿠팡이 에러 본문을 줄 수 있음 — ffmpeg가 디코딩에 실패하면 전체 실행이 죽는다.
    return data is not None and (
        data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8") or data[8:12] == b"WEBP"
    )


def download_image(url: str) -> bytes | None:
    """원본 주소 → 붙여넣은 주소 순서로 받아본다. 둘 다 실패하면 None."""
    for candidate in dict.fromkeys([original_image_url(url), url]):
        try:
            response = requests.get(candidate, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"이미지 다운로드 실패: {e}")
            continue
        if _is_image(response.content):
            return response.content
    return None


def notify(settings: Settings, text: str) -> None:
    """소유자에게 텔레그램으로 알린다. 토큰이 없거나 실패해도 봇은 멈추지 않는다."""
    print(text)
    if not (settings.telegram_bot_token and settings.telegram_owner_chat_id):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_owner_chat_id, "text": f"[TOP3 봇] {text}"},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"텔레그램 알림 실패: {type(e).__name__}")  # URL에 토큰이 있어 예외 본문은 찍지 않는다


def pick_style() -> dict:
    """영상마다 무작위 연출 — 기록해 두고 나중에 성과와 비교한다."""
    return {
        "hook": "quiz" if random.random() < 1 / 3 else "result",
        "palette": random.randrange(len(PALETTES)),
    }


def _runs(beats: list[dict], kinds: tuple[str, ...]) -> list[tuple[int, int]]:
    """kinds에 속하는 장면 중 같은 순위가 이어지는 구간 → (첫 장면, 마지막 장면) 인덱스."""
    runs = []
    for i, beat in enumerate(beats):
        if beat["kind"] not in kinds:
            continue
        if runs and runs[-1][1] == i - 1 and beats[runs[-1][0]]["rank"] == beat["rank"]:
            runs[-1] = (runs[-1][0], i)
        else:
            runs.append((i, i))
    return runs


def compose_top(script: dict, topic: str, photos: list[list[str]], timings: list[dict],
                number: int, style: dict, duration: float):
    """대본·타이밍으로 (화면 장면, 자막 이벤트, 효과음) 을 만든다."""
    beats = script["beats"]
    palette = PALETTES[style["palette"]]
    n = len(photos)

    scenes = []
    for beat, t in zip(beats, timings):
        rank = beat["rank"] or beat["product"] + 1
        scenes.append({
            "start": t["start"], "end": t["end"],
            "photos": photos[beat["product"]], "bg": palette[(rank - 1) % len(palette)],
            "blur": beat["kind"] == "hook" and style["hook"] == "quiz",
            "focus": beat["kind"] == "reveal",
        })

    hook_end = max((t["end"] for b, t in zip(beats, timings) if b["kind"] == "hook"), default=0.0)
    events = title_events(script["hook_lines"], 0, hook_end) if hook_end else []
    header = f"{topic} TOP{n}"
    events.append(event(hook_end, duration, "Head", header, HEADER_Y, rf"\fs{min(84, 980 // len(header))}"))
    for beat, t in zip(beats, timings):
        if beat["kind"] != "hook":
            events += caption_events(beat["text"], t["words"], t["start"], t["end"])

    sfx = []
    whoosh, ding = sfx_path("whoosh"), sfx_path("ding")
    for first, last in _runs(beats, ("item", "reveal")):
        beat = beats[first]
        start, end = timings[first]["start"], timings[last]["end"]
        label = script["labels"][beat["product"]]
        events.append(event(start, end, "Head", f"{beat['rank']}위 · {label}", BADGE_Y,
                            rf"\c{YELLOW}{POP}"))
        sound = ding if beat["kind"] == "reveal" else whoosh
        if sound:
            sfx.append((start, sound))
    for first, last in _runs(beats, ("reveal",)):
        events.append(event(timings[first]["start"], timings[last]["end"], "Cap",
                            f"제품은 프로필 링크 #{number}", CTA_Y, r"\fs60"))
    events += ad_events(duration)
    return scenes, events, sfx


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run() -> str | None:
    """TOP3 봇 1회 실행. 업로드에 성공하면 영상 URL, 아니면 None."""
    settings = load_settings()
    # 토큰이 무효면 Claude 호출·렌더링 전에 바로 실패한다.
    access_token = refresh_access_token(settings)

    records = _load_json(POSTED_VIDEOS_PATH, [])
    today = datetime.date.today().isoformat()
    if records and records[-1]["date"] == today:
        print("오늘 이미 1편을 올렸습니다 — 하루 1편 상한.")
        return None

    posted_ids = load_posted_ids(POSTED_IDS_PATH)
    remaining = [b for b in load_bundles(PRODUCTS_PATH) if bundle_key(b) not in posted_ids]
    if not remaining:
        notify(settings, "남은 묶음이 없어 오늘은 쉽니다 — products.txt에 [주제] 묶음을 추가해주세요.")
        return None
    bundle = remaining[0]
    topic, products = bundle["topic"], bundle["products"]

    no_point = [p["productName"] for p in products if not p["point"]]
    if no_point:
        notify(settings, f"[{topic}] 포인트가 없는 상품이 있어 건너뜁니다: {', '.join(no_point)}")
        return None

    key = bundle_key(bundle)
    work_dir = os.path.join(WORK_DIR, f"{today}-{key[:10]}")
    os.makedirs(work_dir, exist_ok=True)
    photos, first_photos = [], []
    for i, product in enumerate(products):
        paths = []
        for j, url in enumerate(product["images"]):
            data = download_image(url)
            if data:
                if not paths:
                    first_photos.append(data)
                ext = ".png" if data.startswith(b"\x89PNG") else ".webp" if data[8:12] == b"WEBP" else ".jpg"
                paths.append(os.path.join(work_dir, f"photo_{i}_{j}{ext}"))
                with open(paths[-1], "wb") as f:
                    f.write(data)
        photos.append(paths)
    no_photo = [p["productName"] for p, paths in zip(products, photos) if not paths]
    if no_photo:
        notify(settings, f"[{topic}] 상품 사진을 못 받아 건너뜁니다: {', '.join(no_photo)}")
        return None

    style = pick_style()
    try:
        script = write_top_script(settings, topic, products, first_photos, style["hook"])
    except ScriptRejected as e:
        notify(settings, f"[{topic}] 대본 검사 2회 실패로 건너뜁니다: {e}")
        return None

    number = len(records) + 1
    texts = [clean_text(b["text"]) for b in script["beats"]]
    narration = os.path.join(work_dir, "narration.mp3")
    words = synthesize(texts, narration, settings.azure_speech_key, settings.azure_speech_region)
    duration = probe_duration(narration) + TAIL
    timings = timeline(texts, words, duration)

    scenes, events, sfx = compose_top(script, topic, photos, timings, number, style, duration)
    ass = write_ass(events, os.path.join(work_dir, "subs.ass"))
    bgm = pick_bgm()
    video_path = render(scenes, narration, ass, os.path.join(work_dir, "final.mp4"),
                        bgm_path=bgm[0] if bgm else None, sfx=sfx)

    description = build_top_description(products, number, script["keywords"])
    if bgm and bgm[1]:
        description += "\n\n" + bgm[1]  # CC BY 음악 저작자 표시
    video_url = upload_video(
        settings, access_token, video_path, AD_PREFIX + script["title"], description,
        tags=hashtags(script["keywords"]), synthetic=False,
    )

    posted_ids.add(key)
    save_posted_ids(POSTED_IDS_PATH, posted_ids)
    records.append({
        "number": number, "date": today, "topic": topic, "url": video_url,
        "products": [{"name": p["productName"], "label": label, "link": p["productUrl"]}
                     for p, label in zip(products, script["labels"])],
        "style": style,
    })
    with open(POSTED_VIDEOS_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)

    left = len(remaining) - 1
    if left <= LOW_STOCK:
        notify(settings, f"#{number} 업로드 완료 {video_url}\n남은 묶음 {left}개 — products.txt를 채워주세요.")
    return video_url


if __name__ == "__main__":
    result = run()
    if result:
        print(f"업로드 완료: {result}")
