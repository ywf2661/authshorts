import os
import subprocess
import textwrap

# ffmpeg's fontconfig fallback (DejaVu Sans on ubuntu-latest) has no Hangul
# glyphs, so Korean captions would silently render as blank boxes. Pin a
# Hangul-capable font instead (installed via .github/workflows/shortsbot.yml).
FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
# 56px 한글 기준 한 줄 14자 ≈ 800px — 화면 폭과 쇼츠 우측 버튼 영역 안쪽에 들어온다.
CAPTION_CHARS_PER_LINE = 14


def _run_ffmpeg(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(errors="replace"))
        raise


# 이미지 경로 / None(단색 배경) / (영상 경로, 시작 초) 중 하나.
Visual = str | None | tuple[str, float]


def _build_segment(visual: Visual, audio_path: str, text: str, out_path: str, index: int) -> None:
    out_dir = os.path.dirname(out_path) or "."
    caption_path = os.path.join(out_dir, f"caption_{index}.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(textwrap.fill(text, CAPTION_CHARS_PER_LINE))

    drawtext = (
        f"drawtext=textfile='{caption_path}':fontfile='{FONT_PATH}':"
        "fontcolor=white:fontsize=56:line_spacing=14:"
        # 쇼츠 하단 ~25%는 제목·버튼 UI에 가려지므로 화면 62% 높이에 중앙 정렬.
        "box=1:boxcolor=black@0.6:boxborderw=20:x=(w-text_w)/2:y=h*0.62-text_h/2"
    )
    freeze = ""
    if visual is None:
        video_input = ["-f", "lavfi", "-i", "color=c=0x1a1a2e:s=1080x1920"]
    elif isinstance(visual, tuple):
        clip_path, start = visual
        video_input = ["-ss", str(start), "-i", clip_path]
        # 남은 영상이 나레이션보다 짧으면 마지막 프레임을 멈춰서 채운다.
        freeze = "tpad=stop_mode=clone:stop_duration=60,"
    else:
        video_input = ["-loop", "1", "-i", visual]

    cmd = [
        "ffmpeg", "-y",
        *video_input,
        "-i", audio_path,
        "-vf",
        # 정사각형 상품 사진이 잘리지 않게 크롭 대신 여백(단색 배경)을 채운다.
        f"{freeze}scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e,fps=30,{drawtext}",
        # 원본 영상 소리는 버리고 나레이션만 쓴다.
        "-map", "0:v", "-map", "1:a",
        # 2Mbps로 제한 — 텔레그램 봇이 미리보기 영상을 다시 받을 수 있는 20MB 안에 들어오도록.
        "-c:v", "libx264", "-b:v", "2M", "-maxrate", "2M", "-bufsize", "4M",
        "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest",
        out_path,
    ]
    _run_ffmpeg(cmd)


def assemble_video(
    sentences: list[str],
    audio_paths: list[str],
    image_paths: list[Visual],
    out_path: str,
) -> str:
    """문장별 세그먼트(이미지/단색배경/영상 구간 + 오디오 + 자막)를 만들어 이어 붙인다."""
    if not (len(sentences) == len(audio_paths) == len(image_paths)):
        raise ValueError(
            "문장/오디오/이미지 개수가 일치하지 않음: "
            f"{len(sentences)}/{len(audio_paths)}/{len(image_paths)}"
        )

    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    segment_paths = []
    for i, (sentence, audio_path, visual) in enumerate(
        zip(sentences, audio_paths, image_paths), start=1
    ):
        segment_path = os.path.join(out_dir, f"segment_{i}.mp4")
        _build_segment(visual, audio_path, sentence, segment_path, i)
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


def probe_duration(video_path: str) -> float:
    """영상 길이(초)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def extract_frames(video_path: str, out_dir: str, max_frames: int = 30) -> list[tuple[float, str]]:
    """영상 전체에서 균등 간격으로 작은 프레임을 뽑아 (시각 초, 경로) 리스트로 반환한다."""
    os.makedirs(out_dir, exist_ok=True)
    duration = probe_duration(video_path)
    interval = max(1.0, duration / max_frames)
    frames = []
    t = 0.0
    while t < duration and len(frames) < max_frames:
        path = os.path.join(out_dir, f"frame_{len(frames) + 1:03d}.jpg")
        _run_ffmpeg([
            "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", video_path,
            "-frames:v", "1", "-vf", "scale=384:-2", "-q:v", "5", path,
        ])
        frames.append((round(t, 1), path))
        t += interval
    return frames
