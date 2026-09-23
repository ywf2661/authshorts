import html
import os
import urllib.parse

import requests

from config import Settings

# ponytail: hf-inference의 무료 text-to-image 모델은 바뀔 수 있음 —
# https://huggingface.co/docs/inference-providers/en/providers/hf-inference 에서
# 현재 지원 모델로 갱신할 것.
MODEL = "stabilityai/stable-diffusion-3-medium-diffusers"
API_URL = f"https://router.huggingface.co/hf-inference/models/{MODEL}"
# 키 없이 쓰는 무료 대체 — 우하단에 작은 워터마크가 붙는다.
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{}?width=1080&height=1920&nologo=true"

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/ywf2661/autoblog/master/blogbot"


def generate_image(settings: Settings, prompt: str) -> bytes | None:
    """프롬프트로 이미지를 생성해 원본 bytes를 반환한다. HF 실패/키 없음 → Pollinations → None."""
    if settings.hf_api_key:
        try:
            response = requests.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {settings.hf_api_key}",
                    "Content-Type": "application/json",
                },
                json={"inputs": prompt},
                timeout=60,
            )
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            body_text = e.response.text if e.response is not None else "(응답 없음)"
            print(f"HF 이미지 생성 실패, Pollinations로 대체: {e} / 응답: {body_text}")
    return download_image(POLLINATIONS_URL.format(urllib.parse.quote(prompt)), timeout=90)


def download_image(url: str, timeout: int = 30) -> bytes | None:
    """URL의 이미지를 받아 bytes로 반환한다. URL이 없거나 실패하면 None."""
    if not url:
        return None
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.RequestException as e:
        print(f"이미지 다운로드 실패, 건너뜀: {e}")
        return None


def save_generated_image(dir_path: str, filename: str, data: bytes) -> str:
    """이미지를 파일로 저장하고 경로를 반환한다."""
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, filename)
    with open(path, "wb") as f:
        f.write(data)
    return path


def raw_image_url(dir_name: str, filename: str) -> str:
    return f"{GITHUB_RAW_BASE}/{dir_name}/{filename}"


def insert_images(body_html: str, image_urls: list[str | None]) -> str:
    """본문의 [IMAGE_N] 플레이스홀더를 이미지 태그로 치환한다. URL이 없으면 제거."""
    result = body_html
    for i, url in enumerate(image_urls, start=1):
        placeholder = f"[IMAGE_{i}]"
        replacement = (
            f'<img src="{html.escape(url)}" alt="" style="max-width:100%">' if url else ""
        )
        result = result.replace(placeholder, replacement)
    return result
