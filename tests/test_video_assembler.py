from unittest.mock import patch

import pytest

import video_assembler as va


def test_marked_words_tracks_emphasis_across_words():
    assert va.marked_words("올겨울 *이거* 없으면 *대망의 1위*는") == [
        ("올겨울", False), ("이거", True), ("없으면", False), ("대망의", True), ("1위는", True),
    ]
    assert va.clean_text("*이거* 없으면") == "이거 없으면"


def test_caption_events_pop_one_or_two_words_with_yellow_emphasis():
    events = va.caption_events(
        "붙이기만 하면 *외풍*이 막혀요",
        [(1.0, 1.4), (1.4, 1.6), (1.6, 2.0), (2.0, 2.5)], 0.8, 3.0,
    )

    assert len(events) == 2  # 8자 이내로 1~2어절: "붙이기만 하면" / "외풍이 막혀요"
    assert events[0].startswith("Dialogue: 0,0:00:00.80,0:00:01.60,Cap")
    assert "붙이기만 하면" in events[0]
    assert va.YELLOW + "}외풍이" in events[1]
    assert events[1].split(",")[1] == "0:00:01.60"
    assert events[-1].split(",")[2] == "0:00:03.00"


def test_title_events_draw_white_outer_outline_under_every_line():
    events = va.title_events(["안 쓰면", "고생하는"], 0, 2)

    assert len(events) == 4
    assert all(r"\3c" + va.WHITE in e for e in events[0::2])
    assert va.YELLOW in events[1] and va.WHITE in events[3].split(r"\c")[-1]


def test_write_ass_uses_bundled_font_names(tmp_path):
    path = va.write_ass(va.ad_events(10), str(tmp_path / "s.ass"))
    text = open(path, encoding="utf-8").read()

    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert "NanumGothicExtraBold" in text and "Black Han Sans" in text
    assert text.count("쿠팡 파트너스") == 2  # 첫 2초 + 마지막 2초


def test_cuts_split_photo_scenes_into_two_second_pieces_and_rotate():
    scenes = [
        {"start": 0.0, "end": 4.5, "photos": ["a.jpg", "b.jpg"], "bg": "#fff"},
        {"start": 4.5, "end": 6.0, "photos": ["a.jpg", "b.jpg"], "bg": "#fff"},
        {"start": 6.0, "end": 9.0, "clip": "v.mp4", "offset": 2.0},
    ]

    cuts = va._cuts(scenes)

    assert [(round(s, 2), round(e, 2), k) for _, s, e, k in cuts] == [
        (0.0, 1.5, 0), (1.5, 3.0, 1), (3.0, 4.5, 2), (4.5, 6.0, 3), (6.0, 9.0, 0),
    ]


@patch("video_assembler.subprocess.run")
def test_render_builds_cuts_then_one_final_pass(run, tmp_path):
    scenes = [
        {"start": 0.0, "end": 1.0, "photos": ["p.jpg"], "bg": "#FFD93D", "blur": True},
        {"start": 1.0, "end": 2.5, "photos": ["p.jpg"], "bg": "#FFD93D", "focus": True},
    ]
    out = str(tmp_path / "final.mp4")

    va.render(scenes, "n.mp3", str(tmp_path / "s.ass"), out, bgm_path="b.mp3",
              sfx=[(1.0, "ding.mp3")])

    cmds = [c.args[0] for c in run.call_args_list]
    assert len(cmds) == 4  # 컷 2개 + concat + 최종
    assert "boxblur" in cmds[0][cmds[0].index("-filter_complex") + 1]
    assert any(va.FOCUS_LINES[0] == a for a in cmds[1])
    assert cmds[0][cmds[0].index("-frames:v") + 1] == "30"
    assert cmds[1][cmds[1].index("-frames:v") + 1] == "45"
    final = cmds[-1]
    graph = final[final.index("-filter_complex") + 1]
    assert "subtitles=filename='" in graph and ":fontsdir='fonts'" in graph
    assert "adelay=1000|1000" in graph and "[3:a]" in graph  # 효과음은 BGM 다음 입력
    assert "amix=inputs=3" in graph and "loudnorm=I=-14" in graph
    assert run.call_args_list[-1].kwargs["cwd"] == va.ROOT_DIR


@patch("video_assembler.subprocess.run")
def test_render_mixes_original_clip_sound_under_narration(run, tmp_path):
    run.return_value.stdout = "1\n"  # ffprobe: 소리 스트림 있음
    scenes = [
        {"start": 0.0, "end": 1.0, "clip": "a.mp4", "offset": 0.5},
        {"start": 1.0, "end": 2.0, "photos": ["p.jpg"], "bg": "#fff"},
    ]

    va.render(scenes, "n.mp3", str(tmp_path / "s.ass"), str(tmp_path / "final.mp4"), bgm_path="b.mp3")

    cmds = [c.args[0] for c in run.call_args_list if c.args[0][0] == "ffmpeg"]
    clip_sound, photo_sound = cmds[1], cmds[3]
    assert clip_sound[clip_sound.index("-ss") + 1] == "0.50" and "0:a:0" in clip_sound
    assert "anullsrc=r=48000:cl=stereo" in photo_sound  # 사진 컷은 무음으로 길이만 맞춘다
    final = cmds[-1]
    graph = final[final.index("-filter_complex") + 1]
    assert final.count("-i") == 4  # 영상 + 나레이션 + BGM + 원본 소리
    assert f"[3:a]volume={va.ORIGINAL_VOLUME}[o]" in graph and "amix=inputs=3" in graph


def test_ad_label_sits_high_enough_to_dodge_shorts_bottom_ui():
    assert all(f"\\pos(540,{y})" in "".join(va.ad_events(10)) for y in (va.AD_Y, va.AD_Y + 52))
    assert va.AD_Y < va.PHOTO_Y
