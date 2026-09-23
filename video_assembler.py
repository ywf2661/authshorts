import os
import subprocess

# ffmpeg's fontconfig fallback (DejaVu Sans on ubuntu-latest) has no Hangul
# glyphs, so Korean captions would silently render as blank boxes. Pin a
# Hangul-capable font instead (installed via .github/workflows/shortsbot.yml).
FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"


def _run_ffmpeg(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(errors="replace"))
        raise


def _build_segment(
    image_path: str | None, audio_path: str, text: str, out_path: str, index: int
) -> None:
    out_dir = os.path.dirname(out_path) or "."
    caption_path = os.path.join(out_dir, f"caption_{index}.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(text)

    drawtext = (
        f"drawtext=textfile='{caption_path}':fontfile='{FONT_PATH}':"
        "fontcolor=white:fontsize=48:"
        "box=1:boxcolor=black@0.6:boxborderw=16:x=(w-text_w)/2:y=h-200"
    )
    if image_path is None:
        video_input = ["-f", "lavfi", "-i", "color=c=0x1a1a2e:s=1080x1920"]
    else:
        video_input = ["-loop", "1", "-i", image_path]

    cmd = [
        "ffmpeg", "-y",
        *video_input,
        "-i", audio_path,
        "-vf",
        f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,{drawtext}",
        "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac",
        "-pix_fmt", "yuv420p", "-shortest",
        out_path,
    ]
    _run_ffmpeg(cmd)


def assemble_video(
    sentences: list[str],
    audio_paths: list[str],
    image_paths: list[str | None],
    out_path: str,
) -> str:
    """문장별 세그먼트(이미지/단색배경 + 오디오 + 자막)를 만들어 이어 붙인다."""
    if not (len(sentences) == len(audio_paths) == len(image_paths)):
        raise ValueError(
            "문장/오디오/이미지 개수가 일치하지 않음: "
            f"{len(sentences)}/{len(audio_paths)}/{len(image_paths)}"
        )

    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    segment_paths = []
    for i, (sentence, audio_path, image_path) in enumerate(
        zip(sentences, audio_paths, image_paths), start=1
    ):
        segment_path = os.path.join(out_dir, f"segment_{i}.mp4")
        _build_segment(image_path, audio_path, sentence, segment_path, i)
        segment_paths.append(segment_path)

    concat_list_path = os.path.join(out_dir, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for segment_path in segment_paths:
            f.write(f"file '{os.path.abspath(segment_path)}'\n")

    _run_ffmpeg(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_path, "-c", "copy", out_path,
        ]
    )
    return out_path
