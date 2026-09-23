import datetime
import os

from config import load_settings
from coupang_search import search_products
from dedup import hash_link, load_posted_ids, save_posted_ids
from description_builder import build_description
from image_generator import generate_image, save_generated_image
from rss_reader import fetch_feed_entries
from script_writer import pick_and_write_script
from tts import synthesize
from video_assembler import assemble_video
from youtube_api import refresh_access_token, upload_video

FEEDS_PATH = os.path.join(os.path.dirname(__file__), "feeds.txt")
POSTED_IDS_PATH = os.path.join(os.path.dirname(__file__), "shorts_posted_ids.json")
WORK_DIR = "work"
CANDIDATE_LIMIT = 10


def _load_feed_urls(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _pick_candidates(entries: list[dict], posted_ids: set[str], limit: int) -> list[dict]:
    """미게시 항목을 최신순으로 최대 limit개 반환한다."""
    unposted = [e for e in entries if hash_link(e["link"]) not in posted_ids]
    unposted.sort(key=lambda e: e["published"], reverse=True)
    return unposted[:limit]


def run() -> str | None:
    """숏츠봇 1회 실행. 업로드에 성공하면 영상 URL, 아니면 None."""
    settings = load_settings()

    feed_urls = _load_feed_urls(FEEDS_PATH)
    entries = fetch_feed_entries(feed_urls)
    if not entries:
        print(f"수집된 기사가 없습니다 (피드 {len(feed_urls)}개 모두 실패했을 수 있음).")
        return None

    posted_ids = load_posted_ids(POSTED_IDS_PATH)
    candidates = _pick_candidates(entries, posted_ids, CANDIDATE_LIMIT)
    if not candidates:
        print(f"기사 {len(entries)}건을 수집했지만 새로운 후보가 없습니다.")
        return None

    script = pick_and_write_script(settings, candidates)
    link_hash = hash_link(script["chosen_link"])

    today = datetime.date.today().isoformat()
    work_dir = os.path.join(WORK_DIR, f"{today}-{link_hash[:10]}")
    os.makedirs(work_dir, exist_ok=True)

    image_paths = []
    for i, image_prompt in enumerate(script["image_prompts"], start=1):
        image_bytes = generate_image(settings, image_prompt)
        if image_bytes is not None and not (
            image_bytes.startswith(b"\x89PNG") or image_bytes.startswith(b"\xff\xd8")
        ):
            # HF returned something that isn't actually image data (e.g. an
            # error body) -- ffmpeg would fail to decode it and kill the
            # whole run. Fall back to a solid-color background instead.
            image_bytes = None
        if image_bytes is None:
            image_paths.append(None)
            continue
        image_paths.append(save_generated_image(work_dir, f"image_{i}.png", image_bytes))

    audio_paths = synthesize(script["sentences"], work_dir)

    video_path = assemble_video(
        script["sentences"], audio_paths, image_paths, os.path.join(work_dir, "final.mp4")
    )

    summary = " ".join(script["sentences"][:2])
    keywords = script.get("keywords", [])
    products = search_products(keywords[0]) if keywords else []
    description = build_description(summary, products, settings.telegram_channel_url, keywords)

    access_token = refresh_access_token(settings)
    video_url = upload_video(settings, access_token, video_path, script["title"], description)

    posted_ids.add(link_hash)
    save_posted_ids(POSTED_IDS_PATH, posted_ids)

    return video_url


if __name__ == "__main__":
    result = run()
    if result:
        print(f"업로드 완료: {result}")
    else:
        print("새로 업로드할 기사가 없습니다.")
