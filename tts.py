import asyncio
import os
from xml.sax.saxutils import escape

import edge_tts
import requests

# 두 봇 모두 현수 목소리로 통일 — Azure(공식)와 edge-tts(비공식) 둘 다 같은 목소리를 제공한다.
DEFAULT_VOICE = "ko-KR-HyunsuMultilingualNeural"
AZURE_URL = "https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


async def _synthesize_one(text: str, path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


def _synthesize_azure(text: str, path: str, voice: str, key: str, region: str) -> None:
    # 다국어 목소리가 한국어로 읽도록 언어를 못박는다.
    ssml = (
        "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='ko-KR'>"
        f"<voice name='{voice}'><lang xml:lang='ko-KR'>{escape(text)}</lang></voice></speak>"
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
    sentences: list[str], out_dir: str, azure_key: str = "", azure_region: str = "",
    voice: str = DEFAULT_VOICE,
) -> list[str]:
    """문장별로 음성 파일을 생성하고 경로 리스트를 반환한다.

    Azure 키가 있으면 Azure로, 없거나 실패하면 같은 목소리의 edge-tts로 만든다.
    edge-tts까지 실패하면 예외를 그대로 전파한다.
    """
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, sentence in enumerate(sentences, start=1):
        path = os.path.join(out_dir, f"{i}.mp3")
        done = False
        if azure_key and azure_region:
            try:
                _synthesize_azure(sentence, path, voice, azure_key, azure_region)
                done = True
            except (requests.RequestException, RuntimeError) as e:
                print(f"Azure TTS 실패, edge-tts로 대체: {e}")
        if not done:
            asyncio.run(_synthesize_one(sentence, path, voice))
        paths.append(path)
    return paths
