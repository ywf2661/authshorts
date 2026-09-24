"""텔레그램으로 받은 쿠팡템 사용 영상(목소리 없음)을 쇼츠로 편집해 미리보기 → 승인 시 업로드.

1. 캡션에 '상품명 | 쿠팡 링크'를 적어 봇에게 영상을 보낸다.
2. 봇이 장면을 골라 나레이션·자막을 입힌 미리보기를 [업로드]/[취소] 버튼과 함께 보내준다.
3. [업로드]를 누르면 다음 실행 때 유튜브에 올리고 링크를 답장한다.
"""
import json
import os
import sys
import traceback

import requests

from config import Settings, load_settings
from description_builder import build_description, hashtags
from main import AD_PREFIX, TAIL, parse_product_line
from script_writer import write_clip_script
from tts import synthesize, timeline
from video_assembler import (
    BGM_DIR, ad_events, bgm_credit, caption_events, clean_text, extract_frames, pick_bgm,
    probe_duration, render, title_events, write_ass,
)
from youtube_api import refresh_access_token, upload_video

WORK_DIR = "work"
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 텔레그램 봇 getFile 한도

HELP_TEXT = (
    "쿠팡템 사용 영상을 보내주세요 (목소리 없이 찍은 영상).\n"
    "캡션에 '상품명 | 쿠팡 파트너스 링크'를 꼭 적어주세요.\n"
    "예) 몬스터겔 투명 케이스 | https://link.coupang.com/a/xxxx\n"
    "※ '파일'이 아니라 일반 동영상으로 보내야 20MB 안으로 압축돼요."
)


def _tg(settings: Settings, method: str, files=None, **params):
    """텔레그램 Bot API 호출. 에러 메시지에 토큰이 든 URL이 새지 않게 감싼다."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"
    try:
        if files:
            response = requests.post(url, data=params, files=files, timeout=120)
        else:
            response = requests.post(url, json=params, timeout=60)
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        raise RuntimeError(f"텔레그램 {method} 요청 실패: {type(e).__name__}") from None
    if not data.get("ok"):
        raise RuntimeError(f"텔레그램 {method} 실패: {data.get('description')}")
    return data["result"]


def _send(settings: Settings, chat_id, text: str) -> None:
    _tg(settings, "sendMessage", chat_id=chat_id, text=text)


def _download(settings: Settings, file_id: str, dest: str) -> str:
    file_path = _tg(settings, "getFile", file_id=file_id)["file_path"]
    url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"텔레그램 파일 다운로드 실패: {type(e).__name__}") from None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(response.content)
    return dest


def _preview_caption(
    title: str, product: dict, summary: str, bgm_name: str = "", tags: list[str] = ()
) -> str:
    caption = (
        f"제목: {title}\n상품: {product['productName']} | {product['productUrl']}\n"
        f"태그: {' '.join(tags)}\n음악: {bgm_name}\n요약: {summary}"
    )
    return caption[:1024]  # 텔레그램 캡션 최대 길이


def _parse_preview_caption(caption: str) -> dict:
    """미리보기 캡션에서 제목·상품·요약·음악·태그를 되살린다 — 상태를 따로 저장하지 않기 위해."""
    fields = {}
    for line in caption.split("\n"):
        key, sep, value = line.partition(": ")
        if sep:
            fields[key] = value
    product = parse_product_line(fields.get("상품", ""))
    if not fields.get("제목") or product is None:
        raise ValueError("미리보기 캡션을 해석할 수 없어요. 영상을 다시 보내주세요.")
    return {
        "title": fields["제목"],
        "product": product,
        "summary": fields.get("요약", ""),
        "bgm_name": fields.get("음악", ""),
        "tags": fields.get("태그", "").split(),
    }


def _make_preview(settings: Settings, chat_id, video: dict, product: dict) -> None:
    work_dir = os.path.join(WORK_DIR, f"clip-{video['file_unique_id']}")
    source = _download(settings, video["file_id"], os.path.join(work_dir, "source.mp4"))

    duration = probe_duration(source)
    frames = []
    for t, path in extract_frames(source, os.path.join(work_dir, "frames")):
        with open(path, "rb") as f:
            frames.append((t, f.read()))
    script = write_clip_script(settings, product, frames, duration)
    segments = script["segments"]

    texts = [clean_text(seg["text"]) for seg in segments]
    narration = os.path.join(work_dir, "narration.mp3")
    words = synthesize(texts, narration, settings.azure_speech_key, settings.azure_speech_region)
    total = probe_duration(narration) + TAIL
    timings = timeline(texts, words, total)

    scenes = [{"start": t["start"], "end": t["end"], "clip": source, "offset": seg["start"]}
              for seg, t in zip(segments, timings)]
    # 첫 장면은 큰 훅 문구만, 나머지 장면은 팝 자막.
    hook = script["hook_lines"]
    events = title_events(hook, 0, timings[0]["end"]) if hook else []
    for seg, t in list(zip(segments, timings))[1 if hook else 0:]:
        events += caption_events(seg["text"], t["words"], t["start"], t["end"])
    events += ad_events(total)
    bgm = pick_bgm()
    final = render(
        scenes, narration, write_ass(events, os.path.join(work_dir, "subs.ass")),
        os.path.join(work_dir, "final.mp4"), bgm_path=bgm[0] if bgm else None,
    )
    bgm_name = os.path.splitext(os.path.basename(bgm[0]))[0] if bgm else ""

    summary = " ".join(texts[:2])
    keyboard = {"inline_keyboard": [[
        {"text": "✅ 업로드", "callback_data": "upload"},
        {"text": "❌ 취소", "callback_data": "cancel"},
    ]]}
    with open(final, "rb") as f:
        _tg(
            settings, "sendVideo",
            files={"video": f},
            chat_id=chat_id,
            caption=_preview_caption(
                script["title"], product, summary, bgm_name, hashtags(script.get("keywords", []))
            ),
            reply_markup=json.dumps(keyboard),
            supports_streaming="true",
        )


def _upload_preview(settings: Settings, chat_id, message: dict) -> None:
    preview = _parse_preview_caption(message.get("caption", ""))
    bgm_name = preview["bgm_name"]
    path = _download(
        settings, message["video"]["file_id"],
        os.path.join(WORK_DIR, f"upload-{message['message_id']}", "final.mp4"),
    )
    description = build_description(
        preview["summary"], preview["product"], settings.telegram_channel_url, preview["tags"]
    )
    credit = bgm_credit(os.path.join(BGM_DIR, bgm_name + ".mp3")) if bgm_name else ""
    if credit:
        description += "\n\n" + credit  # CC BY 음악 저작자 표시
    access_token = refresh_access_token(settings)
    video_url = upload_video(
        settings, access_token, path, AD_PREFIX + preview["title"], description, tags=preview["tags"]
    )
    _send(settings, chat_id, f"✅ 업로드 완료: {video_url}")


def _handle_callback(settings: Settings, query: dict, handled: set) -> None:
    if str(query["from"]["id"]) != settings.telegram_owner_chat_id:
        return
    message = query["message"]
    chat_id = message["chat"]["id"]
    if message["message_id"] in handled:  # 같은 배치에서 버튼 연타 → 중복 업로드 방지
        return
    handled.add(message["message_id"])
    try:
        _tg(settings, "answerCallbackQuery", callback_query_id=query["id"])
    except RuntimeError:
        pass  # 다음 실행까지 기다리는 사이 쿼리가 만료될 수 있음 — 무시해도 됨
    _tg(settings, "editMessageReplyMarkup", chat_id=chat_id, message_id=message["message_id"],
        reply_markup={"inline_keyboard": []})

    if query.get("data") == "upload":
        _send(settings, chat_id, "⏫ 유튜브에 올리는 중...")
        _upload_preview(settings, chat_id, message)
    else:
        _send(settings, chat_id, "취소했어요.")


def _handle_message(settings: Settings, message: dict) -> None:
    chat_id = str(message["chat"]["id"])
    if chat_id != settings.telegram_owner_chat_id:
        # 초기 설정용: 봇에게 아무 말이나 보내면 자기 chat id를 알려준다. 처리는 하지 않는다.
        _send(settings, chat_id, f"이 봇은 비공개입니다. (내 chat id: {chat_id})")
        return

    video = message.get("video")
    document = message.get("document") or {}
    if video is None and document.get("mime_type", "").startswith("video/"):
        video = document
    product = parse_product_line(message.get("caption", ""))
    if video is None or product is None:
        _send(settings, chat_id, HELP_TEXT)
        return
    if video.get("file_size", 0) > MAX_DOWNLOAD_BYTES:
        _send(settings, chat_id, "영상이 20MB를 넘어요. '파일'이 아니라 일반 동영상으로 다시 보내주세요.")
        return

    _send(settings, chat_id, "🎬 편집 시작! 몇 분 뒤 미리보기를 보내드릴게요.")
    _make_preview(settings, chat_id, video, product)


def _fetch_updates(settings: Settings) -> list[dict]:
    return _tg(settings, "getUpdates", timeout=0, allowed_updates=["message", "callback_query"])


def run() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("필수 환경변수 누락: TELEGRAM_BOT_TOKEN")

    updates = _fetch_updates(settings)
    if not updates:
        print("새 메시지 없음")
        return
    # 먼저 확인 처리 — 처리 중 실패해도 같은 메시지를 매번 다시 처리하지 않도록.
    _tg(settings, "getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)

    handled: set = set()
    for update in updates:
        chat_id = None
        try:
            if "callback_query" in update:
                chat_id = update["callback_query"]["message"]["chat"]["id"]
                _handle_callback(settings, update["callback_query"], handled)
            elif "message" in update:
                chat_id = update["message"]["chat"]["id"]
                _handle_message(settings, update["message"])
        except Exception as e:
            traceback.print_exc()
            if chat_id is not None and str(chat_id) == settings.telegram_owner_chat_id:
                _send(settings, chat_id, f"⚠️ 처리 실패: {e}")


if __name__ == "__main__":
    if "--peek" in sys.argv:
        # 워크플로에서 ffmpeg 설치 전에 새 메시지가 있는지만 확인 (확인 처리는 하지 않음).
        settings = load_settings()
        if not settings.telegram_bot_token:
            # 토큰을 아직 안 넣었으면 15분마다 실패 메일이 가지 않게 조용히 건너뛴다.
            print("TELEGRAM_BOT_TOKEN이 없어서 건너뜀 (Repository secrets에 등록했는지 확인)")
            has_updates = False
        else:
            bot_name = _tg(settings, "getMe")["username"]
            count = len(_fetch_updates(settings))
            print(f"봇 @{bot_name}: 새 메시지 {count}건 (이 봇에게 보냈는지 확인)")
            has_updates = count > 0
        print(f"has_updates={str(has_updates).lower()}")
        output = os.getenv("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write(f"has_updates={str(has_updates).lower()}\n")
    else:
        run()
