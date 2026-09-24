"""쇼츠 조립 (두 봇 공용): 장면별 무음 클립 → 이어 붙이기 → ASS 자막 번인 + 소리 믹스 1패스."""
import glob
import math
import os
import random
import re
import subprocess

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
# ffmpeg 기본 폰트에는 한글이 없다 — 저장소의 한글 폰트(OFL)를 fontsdir로 넘기고 ASS에서 이름으로 쓴다.
FONT_DIR = os.path.join(ROOT_DIR, "fonts")
CAPTION_FONT = "NanumGothicExtraBold"
TITLE_FONT = "Black Han Sans"
FOCUS_LINES = [os.path.join(ROOT_DIR, "effects", f"focus_lines_{i}.png") for i in (1, 2)]
BGM_DIR = os.path.join(ROOT_DIR, "bgm")
SFX_DIR = os.path.join(ROOT_DIR, "sfx")
BGM_VOLUME = 0.18  # 나레이션보다 약 16dB 작게 — 들리되 목소리를 가리지 않는 선 (실측)
SFX_VOLUME = 0.6

W, H, FPS = 1080, 1920, 30
PHOTO_Y = 420  # 1:1 상품 사진(1080) 위치 — 위는 헤더·순위, 아래는 광고 표기
MAX_CUT = 2.0  # 사진 장면은 2초 이하 컷으로 나눠 컷마다 움직임을 바꾼다

# 화면 좌표 (PlayRes = 1080x1920)
HEADER_Y, CTA_Y, BADGE_Y, CAPTION_Y, AD_Y = 170, 320, 510, 1330, 1540
CAPTION_MAX_CHARS = 8
YELLOW = "&H00E4FF&"  # ASS 색은 BGR — #FFE400
WHITE = "&HFFFFFF&"
BLACK = "&H000000&"
POP = r"\fscx70\fscy70\t(0,100,\fscx100\fscy100)"
AD_LINES = ["광고", "쿠팡 파트너스 활동으로 수수료를 받을 수 있음"]


def _run_ffmpeg(cmd: list[str], cwd: str | None = None) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, cwd=cwd)
    except subprocess.CalledProcessError as e:
        print(e.stderr.decode(errors="replace")[-3000:])
        raise


# ---------- 글자 (ASS) ----------

def marked_words(text: str) -> list[tuple[str, bool]]:
    """'*강조어*' 표시가 든 대사를 (어절, 강조 여부)로. 어절 수는 표시를 지운 text.split()과 같다."""
    words, emph = [], False
    for raw in text.split():
        word_emph = emph or raw.startswith("*")
        emph ^= raw.count("*") % 2 == 1
        word = raw.replace("*", "")
        if word:
            words.append((word, word_emph))
    return words


def clean_text(text: str) -> str:
    return " ".join(w for w, _ in marked_words(text))


def _ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _safe(text: str) -> str:
    return re.sub(r"[{}\\]", "", text)


def event(start: float, end: float, style: str, text: str, y: int, tags: str = "", layer: int = 0) -> str:
    return f"Dialogue: {layer},{_ts(start)},{_ts(end)},{style},,0,0,0,,{{\\pos(540,{y}){tags}}}{text}"


def title_events(lines: list[str], start: float, end: float, y_center: int = H // 2) -> list[str]:
    """큰 제목 — 노란 글씨(여러 줄이면 마지막 줄은 흰 글씨), 검은 테두리 + 흰 바깥 테두리."""
    size = min(170, 960 // max(len(line) for line in lines))  # 가장 긴 줄이 화면 폭에 맞도록
    line_h = int(size * 1.15)
    outer, inner = max(8, size * 24 // 170), max(4, size * 11 // 170)
    top = y_center - (len(lines) - 1) * line_h // 2
    events = []
    for j, line in enumerate(lines):
        y = top + j * line_h
        color = WHITE if j == len(lines) - 1 and len(lines) > 1 else YELLOW
        # 흰 바깥 테두리를 먼저 크게 그리고, 그 위에 검은 테두리 + 글씨를 덮는다.
        events.append(event(start, end, "Title", _safe(line), y,
                            rf"\fs{size}\bord{outer}\3c{WHITE}\c{WHITE}", layer=0))
        events.append(event(start, end, "Title", _safe(line), y,
                            rf"\fs{size}\bord{inner}\3c{BLACK}\c{color}", layer=1))
    return events


def caption_events(text: str, word_times: list[tuple[float, float]], start: float, end: float) -> list[str]:
    """어절 1~2개(8자 이내)씩 팝 자막. '*강조어*'는 노랑."""
    words = marked_words(text)
    chunks, i = [], 0
    while i < len(words):
        n = 2 if i + 1 < len(words) and len(words[i][0]) + len(words[i + 1][0]) + 1 <= CAPTION_MAX_CHARS else 1
        chunks.append((i, words[i:i + n]))
        i += n
    events = []
    for k, (i, chunk) in enumerate(chunks):
        t0 = start if k == 0 else word_times[i][0]
        t1 = end if k == len(chunks) - 1 else word_times[chunks[k + 1][0]][0]
        text = " ".join(
            (rf"{{\c{YELLOW}}}{_safe(w)}{{\c{WHITE}}}" if emph else _safe(w)) for w, emph in chunk
        )
        events.append(event(t0, t1, "Cap", text, CAPTION_Y, POP))
    return events


def ad_events(duration: float) -> list[str]:
    """첫 2초와 마지막 2초에 광고 표기."""
    events = []
    for start, end in ((0, min(2, duration)), (max(0, duration - 2), duration)):
        for j, line in enumerate(AD_LINES):
            events.append(event(start, end, "Small", line, AD_Y + j * 50))
    return events


def write_ass(events: list[str], path: str) -> str:
    style = (
        "Style: {name},{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,{bord},0,5,0,0,0,1"
    )
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style.format(name="Cap", font=CAPTION_FONT, size=84, bord=7),
        style.format(name="Title", font=TITLE_FONT, size=150, bord=11),
        style.format(name="Head", font=TITLE_FONT, size=84, bord=8),
        style.format(name="Small", font=CAPTION_FONT, size=38, bord=4),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


# ---------- 화면 ----------

_CENTER = ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)")


def _zoom_preset(k: int, frames: int) -> tuple[str, str, str]:
    """컷마다 돌려 쓰는 움직임: 천천히 확대 / 1.12배 펀치 / 살짝 옆으로 이동."""
    return [
        (f"1+0.1*on/{frames}", *_CENTER),
        ("min(1.12,1+0.04*on)", *_CENTER),
        ("1.1", f"(iw-iw/zoom)*on/{frames}", _CENTER[1]),
    ][k % 3]


def _photo_cut_cmd(photo: str, bg: str, frames: int, preset: int, blur: bool, focus: bool, out: str):
    z, x, y = _zoom_preset(preset, frames)
    # zoompan 떨림 방지: 먼저 2배로 키운 뒤 확대·이동한다. 사진이 정사각형이 아니면 흰 여백을 채운다.
    graph = (
        "[1:v]scale=2160:2160:force_original_aspect_ratio=decrease,"
        "pad=2160:2160:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,"
        + ("boxblur=40:3," if blur else "")
        + f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s=1080x1080:fps={FPS}[p];"
        f"[0:v][p]overlay=0:{PHOTO_Y}"
    )
    inputs = ["-f", "lavfi", "-i", f"color=c=0x{bg.lstrip('#')}:s={W}x{H}:r={FPS}",
              "-loop", "1", "-framerate", str(FPS), "-i", photo]
    if focus:
        # 1위 공개: 만화 집중선 두 장을 번갈아 띄워 움직이는 느낌.
        graph += "[v0];[v0][2:v]overlay=enable='lt(mod(n,6),3)'[v1];[v1][3:v]overlay=enable='gte(mod(n,6),3)'"
        for png in FOCUS_LINES:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", png]
    return ["ffmpeg", "-y", *inputs, "-filter_complex", graph + "[v]", "-map", "[v]",
            *_cut_encode(frames), out]


def _clip_cut_cmd(path: str, offset: float, frames: int, out: str):
    # 남은 영상이 장면보다 짧으면 마지막 프레임을 멈춰서 채운다. 원본 소리는 버린다.
    vf = ("tpad=stop_mode=clone:stop_duration=60,"
          f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={FPS}")
    return ["ffmpeg", "-y", "-ss", f"{offset:.2f}", "-i", path, "-vf", vf, "-map", "0:v",
            *_cut_encode(frames), out]


def _cut_encode(frames: int) -> list[str]:
    return ["-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


def _cuts(scenes: list[dict]) -> list[tuple[dict, float, float, int]]:
    """사진 장면을 2초 이하 컷으로 나눈다 → (장면, 시작, 끝, 같은 사진 묶음 안에서 몇 번째 컷)."""
    cuts, counters = [], {}
    for scene in scenes:
        s, e = scene["start"], scene["end"]
        n = max(1, math.ceil((e - s) / MAX_CUT - 1e-9)) if scene.get("photos") else 1
        key = tuple(scene.get("photos", ()))
        for j in range(n):
            k = counters.get(key, 0)
            counters[key] = k + 1
            cuts.append((scene, s + (e - s) * j / n, s + (e - s) * (j + 1) / n, k))
    return cuts


def render(
    scenes: list[dict], narration_path: str, ass_path: str, out_path: str,
    bgm_path: str | None = None, sfx: list[tuple[float, str]] = (),
) -> str:
    """장면을 이어 붙이고 자막·나레이션·BGM·효과음을 한 번에 입힌다.

    scene: {"start", "end"} + 사진 장면 {"photos": [경로], "bg": "#RRGGBB", "blur", "focus"}
                            또는 영상 장면 {"clip": 경로, "offset": 시작초}.
    """
    out_dir = os.path.abspath(os.path.dirname(out_path) or ".")
    os.makedirs(out_dir, exist_ok=True)
    duration = scenes[-1]["end"]

    cut_paths = []
    for i, (scene, s, e, k) in enumerate(_cuts(scenes)):
        frames = round(e * FPS) - round(s * FPS)  # 누적 반올림 — 컷이 많아도 소리와 어긋나지 않는다
        if frames <= 0:
            continue
        path = os.path.join(out_dir, f"cut_{i:03d}.mp4")
        if scene.get("photos"):
            photos = scene["photos"]
            cmd = _photo_cut_cmd(photos[k % len(photos)], scene["bg"], frames, k,
                                 scene.get("blur", False), scene.get("focus", False), path)
        else:
            cmd = _clip_cut_cmd(scene["clip"], scene["offset"] + (s - scene["start"]), frames, path)
        _run_ffmpeg(cmd)
        cut_paths.append(path)

    concat_list = os.path.join(out_dir, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        f.writelines(f"file '{p}'\n" for p in cut_paths)
    joined = os.path.join(out_dir, "joined.mp4")
    _run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", joined])

    inputs = ["-i", joined, "-i", os.path.abspath(narration_path)]
    audio = ["[1:a]apad[n]"]
    mix = ["[n]"]
    if bgm_path:
        inputs += ["-stream_loop", "-1", "-i", os.path.abspath(bgm_path)]
        audio.append(f"[2:a]volume={BGM_VOLUME},afade=t=out:st={max(0.0, duration - 1.5):.2f}:d=1.5[b]")
        mix.append("[b]")
    for idx, (t, path) in enumerate(sfx, start=3 if bgm_path else 2):
        inputs += ["-i", os.path.abspath(path)]
        ms = round(t * 1000)
        audio.append(f"[{idx}:a]adelay={ms}|{ms},volume={SFX_VOLUME}[s{idx}]")
        mix.append(f"[s{idx}]")
    # subtitles 필터는 윈도 경로(C:)의 콜론을 못 읽는다 — 저장소 폴더에서 상대경로로 넘긴다.
    ass_rel = os.path.relpath(os.path.abspath(ass_path), ROOT_DIR).replace("\\", "/")
    graph = ";".join([
        f"[0:v]subtitles=filename='{ass_rel}':fontsdir='fonts'[v]",
        *audio,
        f"{''.join(mix)}amix=inputs={len(mix)}:duration=first:normalize=0,"
        "loudnorm=I=-14:TP=-1.5:LRA=11[a]",
    ])
    _run_ffmpeg([
        "ffmpeg", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
        "-t", f"{duration:.2f}",
        # 2Mbps로 제한 — 텔레그램 봇이 미리보기 영상을 다시 받을 수 있는 20MB 안에 들어오도록.
        "-c:v", "libx264", "-b:v", "2M", "-maxrate", "2M", "-bufsize", "4M", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        os.path.abspath(out_path),
    ], cwd=ROOT_DIR)
    return out_path


# ---------- 소리 파일 ----------

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


def sfx_path(name: str) -> str | None:
    """sfx/ 폴더의 효과음 (whoosh·ding 등). 없으면 None — 효과음 없이 진행."""
    found = sorted(glob.glob(os.path.join(SFX_DIR, f"{name}.*")))
    return found[0] if found else None


def probe_duration(video_path: str) -> float:
    """영상·음성 길이(초)."""
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
