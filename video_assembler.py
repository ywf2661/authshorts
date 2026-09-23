import os
import subprocess
import textwrap

# ffmpeg 기본 폰트에는 한글이 없어서 자막이 빈 네모로 나온다 — 저장소의 한글 폰트(OFL)를 지정한다.
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
CAPTION_FONT = os.path.join(FONT_DIR, "NanumGothic-ExtraBold.ttf")
TITLE_FONT = os.path.join(FONT_DIR, "BlackHanSans-Regular.ttf")
# 78px 한글 기준 한 줄 12자 ≈ 940px — 화면 폭 안쪽에 들어온다.
CAPTION_CHARS_PER_LINE = 12
CAPTION_FONT_SIZE = 78
# 쇼츠 상단 재생·음량 버튼(~8%) 바로 아래, 레퍼런스처럼 화면 위쪽 20% 높이.
CAPTION_CENTER_Y = 0.2
TITLE_YELLOW = "0xFFE400"


def _run_ffmpeg(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(errors="replace"))
        raise


# 이미지 경로 / None(단색 배경) / (영상 경로, 시작 초) 중 하나.
Visual = str | None | tuple[str, float]


def _drawtext(text_path: str, font: str, size: int, color: str, border: int,
              border_color: str, y: str) -> str:
    return (
        f"drawtext=textfile='{text_path}':fontfile='{font}':fontsize={size}:"
        f"fontcolor={color}:borderw={border}:bordercolor={border_color}:"
        f"x=(w-text_w)/2:y={y}"
    )


def _write(path: str, text: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _caption_filters(text: str, out_dir: str, index: int) -> list[str]:
    """흰 글씨 + 검은 테두리 자막. 줄마다 따로 그려야 각 줄이 가운데 정렬된다."""
    lines = textwrap.wrap(text, CAPTION_CHARS_PER_LINE)
    line_h = int(CAPTION_FONT_SIZE * 1.3)
    top = f"h*{CAPTION_CENTER_Y}-{len(lines) * line_h // 2}"
    return [
        _drawtext(
            _write(os.path.join(out_dir, f"caption_{index}_{j}.txt"), line),
            CAPTION_FONT, CAPTION_FONT_SIZE, "white", 7, "black", f"{top}+{j * line_h}",
        )
        for j, line in enumerate(lines)
    ]


def _title_filters(lines: list[str], out_dir: str) -> list[str]:
    """첫 장면 화면 가운데의 큰 제목 — 노란 글씨(마지막 줄은 흰 글씨), 검은 테두리 + 흰 바깥 테두리."""
    size = min(170, 960 // max(len(line) for line in lines))  # 가장 긴 줄이 화면 폭에 맞도록
    line_h = int(size * 1.15)
    top = f"h*0.5-{len(lines) * line_h // 2}"
    filters = []
    for j, line in enumerate(lines):
        path = _write(os.path.join(out_dir, f"title_{j}.txt"), line)
        y = f"{top}+{j * line_h}"
        last = j == len(lines) - 1 and len(lines) > 1
        if not last:
            filters.append(_drawtext(path, TITLE_FONT, size, "white", 24, "white", y))
        filters.append(_drawtext(path, TITLE_FONT, size, "white" if last else TITLE_YELLOW, 11, "black", y))
    return filters


def _build_segment(
    visual: Visual, audio_path: str, text: str, out_path: str, index: int,
    title_lines: list[str] | None = None,
) -> None:
    out_dir = os.path.dirname(out_path) or "."
    overlays = _caption_filters(text, out_dir, index)
    if title_lines:
        overlays += _title_filters(title_lines, out_dir)
    drawtext = ",".join(overlays)

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
    title_lines: list[str] | None = None,
) -> str:
    """문장별 세그먼트(이미지/단색배경/영상 구간 + 오디오 + 자막)를 만들어 이어 붙인다.

    title_lines가 있으면 첫 장면 가운데에 큰 제목으로 박는다.
    """
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
        # 큰 제목은 첫 장면(첫 문장)에만 띄운다.
        _build_segment(visual, audio_path, sentence, segment_path, i, title_lines if i == 1 else None)
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
