import asyncio
import os

import edge_tts

DEFAULT_VOICE = "ko-KR-SunHiNeural"


async def _synthesize_one(text: str, path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(path)


def synthesize(sentences: list[str], out_dir: str, voice: str = DEFAULT_VOICE) -> list[str]:
    """문장별로 음성 파일을 생성하고 경로 리스트를 반환한다. 실패 시 예외를 그대로 전파한다."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i, sentence in enumerate(sentences, start=1):
        path = os.path.join(out_dir, f"{i}.mp3")
        asyncio.run(_synthesize_one(sentence, path, voice))
        paths.append(path)
    return paths
