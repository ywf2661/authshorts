import asyncio
import re
from xml.sax.saxutils import escape

import edge_tts
import requests

# 두 봇 모두 현수 목소리로 통일 — edge-tts(비공식)와 Azure(공식) 둘 다 같은 목소리를 제공한다.
DEFAULT_VOICE = "ko-KR-HyunsuMultilingualNeural"
RATE = "+20%"
AZURE_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
TICKS_PER_SECOND = 10_000_000  # edge-tts offset/duration 단위는 100ns


def speech_text(texts: list[str]) -> str:
    """장면 대사를 한 번에 읽을 한 덩어리로 — 문장부호가 없으면 마침표를 붙여 장면 사이에 쉼을 준다."""
    return " ".join(t if t[-1] in ".?!~" else t + "." for t in texts)


async def _synthesize_edge(text: str, path: str, voice: str) -> list[tuple[float, float, str]]:
    communicate = edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary")
    words = []
    with open(path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / TICKS_PER_SECOND
                words.append((start, start + chunk["duration"] / TICKS_PER_SECOND, chunk["text"]))
    return words


def _synthesize_azure(text: str, path: str, voice: str, key: str, region: str) -> None:
    # 다국어 목소리가 한국어로 읽도록 언어를 못박는다.
    ssml = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='ko-KR'>"
        f"<voice name='{voice}'><lang xml:lang='ko-KR'><prosody rate='{RATE}'>{escape(text)}"
        "</prosody></lang></voice></speak>"
    )
    response = requests.post(
        AZURE_URL.format(region=region),
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            "User-Agent": "authshorts",
        },
        data=ssml.encode("utf-8"),
        timeout=60,
    )
    if not response.ok:
        # 응답 본문만 남긴다 (키는 헤더에만 있어 로그에 찍히지 않음).
        raise RuntimeError(f"Azure TTS 실패 {response.status_code}: {response.text[:200]}")
    with open(path, "wb") as f:
        f.write(response.content)


def synthesize(
    texts: list[str], path: str, azure_key: str = "", azure_region: str = "",
    voice: str = DEFAULT_VOICE,
) -> list[tuple[float, float, str]] | None:
    """장면 대사 전체를 mp3 하나로 합성하고 어절별 (시작, 끝, 글자)를 반환한다.

    edge-tts가 실패하면 Azure로 합성하고 None(타이밍 없음 → 글자 수 비례)을 반환한다.
    """
    text = speech_text(texts)
    try:
        return asyncio.run(_synthesize_edge(text, path, voice))
    except Exception as e:  # edge-tts는 비공식이라 실패 유형이 다양하다
        if not (azure_key and azure_region):
            raise
        print(f"edge-tts 실패, Azure로 대체: {e}")
    _synthesize_azure(text, path, voice, azure_key, azure_region)
    return None


def _norm(s: str) -> str:
    return re.sub(r"[\W_]", "", s)


def _aligned_token_times(tokens, words):
    """어절 이벤트를 대본 어절에 순서대로 맞춰 어절별 (시작, 끝). 너무 어긋나면 None."""
    stream = "".join(_norm(t) for t in tokens)
    starts, ends = [None] * len(stream), [None] * len(stream)
    pos = matched = 0
    for w_start, w_end, text in words:
        w = _norm(text)
        idx = stream.find(w, pos) if w else -1
        if idx < 0 or idx - pos > 3:
            continue
        for i in range(idx, idx + len(w)):
            starts[i], ends[i] = w_start, w_end
        pos = idx + len(w)
        matched += len(w)
    if not stream or matched < 0.8 * len(stream):
        return None
    # 매칭 못 한 글자는 앞 글자 시각을 물려받는다 (맨 앞이면 뒤 글자).
    for arr in (starts, ends):
        first = next(v for v in arr if v is not None)
        prev = first
        for i, v in enumerate(arr):
            arr[i] = prev = v if v is not None else prev
    times, i, prev_end = [], 0, 0.0
    for t in tokens:
        n = len(_norm(t))
        if n == 0:  # 문장부호만 있는 어절
            times.append((prev_end, prev_end))
            continue
        times.append((starts[i], ends[i + n - 1]))
        prev_end = ends[i + n - 1]
        i += n
    return times


def _proportional_token_times(tokens, duration):
    # ponytail: 글자 수 비례 — TTS가 숫자를 풀어 읽거나 쉼이 길면 어긋난다. 어절 매칭 실패 때만 쓴다.
    total = sum(len(t) for t in tokens) or 1
    times, t = [], 0.0
    for token in tokens:
        end = t + duration * len(token) / total
        times.append((t, end))
        t = end
    return times


def timeline(texts: list[str], words, duration: float) -> list[dict]:
    """장면별 {"start", "end", "words": [(시작, 끝), ...]} — 어절 수는 text.split()과 같다.

    장면 경계는 앞 장면 마지막 어절 끝과 다음 장면 첫 어절 시작의 중간. 첫 장면은 0, 마지막은 duration.
    """
    beat_tokens = [t.split() for t in texts]
    tokens = [tok for toks in beat_tokens for tok in toks]
    times = (_aligned_token_times(tokens, words) if words else None) \
        or _proportional_token_times(tokens, duration)
    beats, i = [], 0
    for toks in beat_tokens:
        beats.append({"words": times[i:i + len(toks)]})
        i += len(toks)
    for n, beat in enumerate(beats):
        beat["start"] = 0.0 if n == 0 else (beats[n - 1]["words"][-1][1] + beat["words"][0][0]) / 2
    for n, beat in enumerate(beats):
        beat["end"] = duration if n == len(beats) - 1 else beats[n + 1]["start"]
    return beats
