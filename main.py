import datetime
import os

from config import load_settings
from dedup import hash_link, load_posted_ids, save_posted_ids
from description_builder import build_description, hashtags
from image_generator import download_image, generate_image, save_generated_image
from script_writer import write_script
from tts import synthesize
from video_assembler import assemble_video, pick_bgm
from youtube_api import refresh_access_token, upload_video

PRODUCTS_PATH = os.path.join(os.path.dirname(__file__), "products.txt")
POSTED_IDS_PATH = os.path.join(os.path.dirname(__file__), "shorts_posted_ids.json")
WORK_DIR = "work"
AD_PREFIX = "[광고] "  # 공정위 추천·보증 심사지침: 영상 광고는 제목에 경제적 이해관계 표시


def parse_product_line(line: str) -> dict | None:
    """'상품명 | 링크 | 이미지(선택)' 한 줄을 상품 dict로. 형식이 틀리면 None."""
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1].startswith("http"):
        return None
    return {
        "productName": parts[0],
        "productUrl": parts[1],
        "productImage": parts[2] if len(parts) > 2 else "",
    }


def _load_products(path: str) -> list[dict]:
    """products.txt를 파일 순서대로 읽는다 (주석·빈 줄 무시, 같은 링크는 한 번만)."""
    seen = set()
    products = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            product = parse_product_line(line)
            if product is None:
                print(f"형식이 잘못된 줄은 건너뜀: {line}")
                continue
            if product["productUrl"] in seen:
                continue
            seen.add(product["productUrl"])
            products.append(product)
    return products


def _pick_product(products: list[dict], posted_ids: set[str]) -> dict | None:
    """아직 안 올린 첫 상품을 반환한다."""
    return next((p for p in products if hash_link(p["productUrl"]) not in posted_ids), None)


def _is_image(data: bytes | None) -> bool:
    # HF/쿠팡이 에러 본문을 줄 수 있음 — ffmpeg가 디코딩에 실패하면 전체 실행이 죽는다.
    return data is not None and (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8"))


def run() -> str | None:
    """숏츠봇 1회 실행. 업로드에 성공하면 영상 URL, 아니면 None."""
    settings = load_settings()

    posted_ids = load_posted_ids(POSTED_IDS_PATH)
    product = _pick_product(_load_products(PRODUCTS_PATH), posted_ids)
    if product is None:
        print("새로 소개할 상품이 없습니다 — products.txt에 상품을 추가하세요.")
        return None

    script = write_script(settings, product)
    link_hash = hash_link(product["productUrl"])

    today = datetime.date.today().isoformat()
    work_dir = os.path.join(WORK_DIR, f"{today}-{link_hash[:10]}")
    os.makedirs(work_dir, exist_ok=True)

    # 첫 장면은 실제 상품 사진, 나머지는 AI 삽화. 둘 중 하나가 실패하면 다른 쪽으로 채운다.
    product_photo = download_image(product.get("productImage", ""))
    image_paths = []
    for i, image_prompt in enumerate(script["image_prompts"], start=1):
        image_bytes = product_photo if i == 1 and _is_image(product_photo) else None
        if image_bytes is None:
            image_bytes = generate_image(settings, image_prompt)
        if not _is_image(image_bytes):
            # AI 이미지까지 실패하면 단색 배경 대신 상품 사진을 재사용.
            image_bytes = product_photo if _is_image(product_photo) else None
        if image_bytes is None:
            image_paths.append(None)
            continue
        image_paths.append(save_generated_image(work_dir, f"image_{i}.png", image_bytes))

    audio_paths = synthesize(script["sentences"], work_dir)

    bgm = pick_bgm()
    video_path = assemble_video(
        script["sentences"], audio_paths, image_paths, os.path.join(work_dir, "final.mp4"),
        title_lines=script.get("cover_lines"),
        emphasis=script.get("emphasis", []),
        bgm_path=bgm[0] if bgm else None,
    )

    summary = " ".join(script["sentences"][:2])
    description = build_description(
        summary, product, settings.telegram_channel_url, script.get("keywords", [])
    )
    if bgm and bgm[1]:
        description += "\n\n" + bgm[1]  # CC BY 음악 저작자 표시

    access_token = refresh_access_token(settings)
    video_url = upload_video(
        settings, access_token, video_path, AD_PREFIX + script["title"], description,
        tags=hashtags(script.get("keywords", [])),
    )

    posted_ids.add(link_hash)
    save_posted_ids(POSTED_IDS_PATH, posted_ids)

    return video_url


if __name__ == "__main__":
    result = run()
    if result:
        print(f"업로드 완료: {result}")
