import glob
import os
import random
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

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FOCUS_LINES = [os.path.join(ROOT_DIR, "effects", f"focus_lines_{i}.png") for i in (1, 2)]
BGM_DIR = os.path.join(ROOT_DIR, "bgm")
BGM_VOLUME = 0.18  # 나레이션보다 약 16dB 작게 — 들리되 목소리를 가리지 않는 선 (실측)


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


def _caption_filters(text: str, out_dir: str, index: int, duration: float) -> list[str]:
    """흰 글씨 + 검은 테두리 자막을 한 번에 한 줄씩, 글자 수 비율로 시간을 나눠 띄운다."""
    # ponytail: 글자 수 비례 타이밍 — 말하는 속도가 들쭉날쭉하면 어긋날 수 있음.
    # 더 정확하게 하려면 edge-tts WordBoundary 이벤트로 줄별 시작 시각을 받아올 것.
    lines = textwrap.wrap(text, CAPTION_CHARS_PER_LINE)
    total = sum(len(line) for line in lines)
    y = f"h*{CAPTION_CENTER_Y}-{CAPTION_FONT_SIZE // 2}"
    filters = []
    start = 0.0
    for j, line in enumerate(lines):
        end = duration if j == len(lines) - 1 else start + duration * len(line) / total
        path = _write(os.path.join(out_dir, f"caption_{index}_{j}.txt"), line)
        filters.append(
            _drawtext(path, CAPTION_FONT, CAPTION_FONT_SIZE, "white", 7, "black", y)
            + f":enable='between(t,{start:.2f},{end:.2f})'"
        )
        start = end
    return filters


def _title_filters(lines: list[str], out_dir: str) -> list[str]:
    """첫 장면 화면 가운데의 큰 제목 — 노란 글씨(마지막 줄은 흰 글씨), 모든 줄에 검은 테두리 + 흰 바깥 테두리."""
    size = min(170, 960 // max(len(line) for line in lines))  # 가장 긴 줄이 화면 폭에 맞도록
    line_h = int(size * 1.15)
    top = f"h*0.5-{len(lines) * line_h // 2}"
    # 테두리 두께도 글자 크기에 비례 (170px 기준 흰 24px / 검은 11px)
    outer, inner = max(8, size * 24 // 170), max(4, size * 11 // 170)
    filters = []
    for j, line in enumerate(lines):
        path = _write(os.path.join(out_dir, f"title_{j}.txt"), line)
        y = f"{top}+{j * line_h}"
        last = j == len(lines) - 1 and len(lines) > 1
        # 흰 바깥 테두리를 먼저 크게 그리고, 그 위에 검은 테두리 + 글씨를 덮는다.
        filters.append(_drawtext(path, TITLE_FONT, size, "white", outer, "white", y))
        filters.append(_drawtext(path, TITLE_FONT, size, "white" if last else TITLE_YELLOW, inner, "black", y))
    return filters


def _build_segment(
    visual: Visual, audio_path: str, text: str, out_path: str, index: int,
    title_lines: list[str] | None = None, emphasis: bool = False,
) -> None:
    out_dir = os.path.dirname(out_path) or "."
    if title_lines:
        # 제목 장면에는 제목만 — 나레이션 자막을 겹치지 않는다.
        overlays = _title_filters(title_lines, out_dir)
    else:
        overlays = _caption_filters(text, out_dir, index, probe_duration(audio_path))

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

    # 정사각형 상품 사진이 잘리지 않게 크롭 대신 여백(단색 배경)을 채운다.
    graph = (
        f"[0:v]{freeze}scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x1a1a2e,fps=30"
    )
    effect_inputs = []
    if emphasis:
        # 강조 장면: 천천히 확대(최대 1.15배) + 만화 집중선 두 장을 번갈아 띄워 움직이는 느낌.
        graph += (
            ",zoompan=z='min(1+0.004*in,1.15)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
            ":d=1:s=1080x1920:fps=30[z];"
            "[z][2:v]overlay=enable='lt(mod(n,6),3)'[e1];"
            "[e1][3:v]overlay=enable='gte(mod(n,6),3)'"
        )
        for png in FOCUS_LINES:
            effect_inputs += ["-loop", "1", "-i", png]
    graph += "," + ",".join(overlays) + "[vout]"

    cmd = [
        "ffmpeg", "-y",
        *video_input,
        "-i", audio_path,
        *effect_inputs,
        "-filter_complex", graph,
        # 원본 영상 소리는 버리고 나레이션만 쓴다.
        "-map", "[vout]", "-map", "1:a",
        # 2Mbps로 제한 — 텔레그램 봇이 미리보기 영상을 다시 받을 수 있는 20MB 안에 들어오도록.
        "-c:v", "libx264", "-b:v", "2M", "-maxrate", "2M", "-bufsize", "4M",
        "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest",
        out_path,
    ]
    _run_ffmpeg(cmd)


def bgm_credit(track_path: str) -> str:
    """곡과 같은 이름의 .txt에 적힌 저작자 표시 (없으면 빈 문자열)."""
    credit_path = os.path.splitext(track_path)[0] + ".txt"
    if not os.path.exists(credit_path):
        return ""
    with open(credit_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def pick_bgm() -> tuple[str, str] | None:
    """bgm/ 폴더에서 무작위 곡 1개와 설명란에 넣을 저작자 표시를 고른다."""
    tracks = sorted(glob.glob(os.path.join(BGM_DIR, "*.mp3")))
    if not tracks:
        return None
    track = random.choice(tracks)
    return track, bgm_credit(track)


def _mix_bgm(video_path: str, bgm_path: str, out_path: str) -> None:
    """나레이션 아래에 BGM을 작게 깔고(짧으면 반복) 끝에서 1.5초 페이드아웃한다."""
    fade_start = max(0.0, probe_duration(video_path) - 1.5)
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", video_path, "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex",
        f"[1:a]volume={BGM_VOLUME},afade=t=out:st={fade_start:.2f}:d=1.5[b];"
        "[0:a][b]amix=inputs=2:duration=first:normalize=0[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        out_path,
    ])


def assemble_video(
    sentences: list[str],
    audio_paths: list[str],
    image_paths: list[Visual],
    out_path: str,
    title_lines: list[str] | None = None,
    emphasis: list[int] = (),
    bgm_path: str | None = None,
) -> str:
    """문장별 세그먼트(이미지/단색배경/영상 구간 + 오디오 + 자막)를 만들어 이어 붙인다.

    title_lines가 있으면 첫 장면에 자막 대신 큰 제목을 박는다.
    emphasis는 확대·집중선 효과를 줄 문장 인덱스(0부터), bgm_path가 있으면 BGM을 깐다.
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
        _build_segment(
            visual, audio_path, sentence, segment_path, i,
            title_lines if i == 1 else None, emphasis=(i - 1) in emphasis,
        )
        segment_paths.append(segment_path)

    concat_list_path = os.path.join(out_dir, "concat_list.txt")
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for segment_path in segment_paths:
            f.write(f"file '{os.path.abspath(segment_path)}'\n")

    joined_path = os.path.join(out_dir, "joined.mp4") if bgm_path else out_path
    _run_ffmpeg(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list_path, "-c", "copy", joined_path,
        ]
    )
    if bgm_path:
        _mix_bgm(joined_path, bgm_path, out_path)
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
