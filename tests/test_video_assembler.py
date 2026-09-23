import os
import subprocess
from unittest.mock import patch

import pytest

import video_assembler
from video_assembler import CAPTION_FONT, FOCUS_LINES, TITLE_FONT, assemble_video, pick_bgm


def _ffmpeg_cmds(mock_run):
    return [c.args[0] for c in mock_run.call_args_list]


def _graph(cmd):
    return cmd[cmd.index("-filter_complex") + 1]


@pytest.fixture
def mock_run():
    # 문장 오디오 길이는 4초로 고정 — ffprobe를 실제로 돌리지 않는다.
    with patch("video_assembler.subprocess.run") as run, \
            patch("video_assembler.probe_duration", return_value=4.0):
        yield run


def test_assemble_video_raises_on_length_mismatch(mock_run, tmp_path):
    with pytest.raises(ValueError, match="일치하지 않음"):
        assemble_video(
            ["문장1", "문장2"], ["a1.mp3"], ["i1.png", "i2.png"], str(tmp_path / "out.mp4")
        )

    mock_run.assert_not_called()


def test_assemble_video_builds_one_segment_per_sentence_and_concats(mock_run, tmp_path):
    out_path = str(tmp_path / "out.mp4")

    result = assemble_video(
        ["문장1", "문장2"], ["a1.mp3", "a2.mp3"], ["i1.png", "i2.png"], out_path
    )

    assert result == out_path
    # 세그먼트 2개 + concat 1개 = ffmpeg 총 3번 호출
    assert mock_run.call_count == 3
    for call in mock_run.call_args_list:
        assert call.kwargs["check"] is True


def test_assemble_video_uses_color_background_when_image_missing(mock_run, tmp_path):
    assemble_video(["문장1"], ["a1.mp3"], [None], str(tmp_path / "out.mp4"))

    assert "lavfi" in _ffmpeg_cmds(mock_run)[0]


def test_captions_show_one_line_at_a_time_split_by_length(mock_run, tmp_path):
    # OpenAI's -- an apostrophe that would have broken the old text='...' escaping.
    assemble_video(["OpenAI's new model"], ["a1.mp3"], ["i1.png"], str(tmp_path / "out.mp4"))

    # 12자 줄바꿈 → 두 줄을 차례로: 12자 + 5자 = 17자, 4초를 글자 수 비율로 나눔
    assert (tmp_path / "caption_1_0.txt").read_text(encoding="utf-8") == "OpenAI's new"
    assert (tmp_path / "caption_1_1.txt").read_text(encoding="utf-8") == "model"
    graph = _graph(_ffmpeg_cmds(mock_run)[0])
    assert graph.count(f"fontfile='{CAPTION_FONT}'") == 2
    assert "enable='between(t,0.00,2.82)'" in graph
    assert "enable='between(t,2.82,4.00)'" in graph
    assert "text='" not in graph


def test_assemble_video_prints_stderr_and_reraises_on_ffmpeg_failure(mock_run, tmp_path, capsys):
    mock_run.side_effect = subprocess.CalledProcessError(
        1, ["ffmpeg"], stderr=b"ffmpeg exploded"
    )

    with pytest.raises(subprocess.CalledProcessError):
        assemble_video(["문장1"], ["a1.mp3"], ["i1.png"], str(tmp_path / "out.mp4"))

    assert "ffmpeg exploded" in capsys.readouterr().out


def test_assemble_video_cuts_clip_segment_and_drops_original_audio(mock_run, tmp_path):
    assemble_video(["문장1"], ["a1.mp3"], [("src.mp4", 3.5)], str(tmp_path / "out.mp4"))

    cmd = _ffmpeg_cmds(mock_run)[0]
    assert cmd[cmd.index("-ss") + 1] == "3.5"
    assert cmd[cmd.index("-ss") + 3] == "src.mp4"
    assert "tpad=stop_mode=clone" in _graph(cmd)
    assert cmd[cmd.index("-map") + 1] == "[vout]"
    assert cmd[cmd.index("-map") + 3] == "1:a"


def test_title_scene_shows_only_title_and_later_scenes_only_captions(mock_run, tmp_path):
    assemble_video(
        ["문장1", "문장2"], ["a1.mp3", "a2.mp3"], ["i1.png", "i2.png"],
        str(tmp_path / "out.mp4"), title_lines=["N통째 쓴", "쿠팡필수템"],
    )

    first, second = _graph(_ffmpeg_cmds(mock_run)[0]), _graph(_ffmpeg_cmds(mock_run)[1])
    assert TITLE_FONT in first and CAPTION_FONT not in first
    assert TITLE_FONT not in second and CAPTION_FONT in second
    assert (tmp_path / "title_1.txt").read_text(encoding="utf-8") == "쿠팡필수템"


def test_emphasis_adds_zoom_and_focus_lines_only_to_chosen_sentence(mock_run, tmp_path):
    assemble_video(
        ["문장1", "문장2"], ["a1.mp3", "a2.mp3"], ["i1.png", "i2.png"],
        str(tmp_path / "out.mp4"), emphasis=[1],
    )

    first, second = _ffmpeg_cmds(mock_run)[:2]
    assert "zoompan" not in _graph(first) and FOCUS_LINES[0] not in first
    assert "zoompan" in _graph(second) and "overlay" in _graph(second)
    assert FOCUS_LINES[0] in second and FOCUS_LINES[1] in second


def test_bgm_is_mixed_after_concat(mock_run, tmp_path):
    out_path = str(tmp_path / "out.mp4")
    assemble_video(["문장1"], ["a1.mp3"], ["i1.png"], out_path, bgm_path="song.mp3")

    concat, mix = _ffmpeg_cmds(mock_run)[1:]
    assert concat[-1].endswith("joined.mp4")
    assert "song.mp3" in mix and "amix" in _graph(mix) and mix[-1] == out_path


def test_pick_bgm_returns_track_with_credit():
    track, credit = pick_bgm()

    assert track.endswith(".mp3") and os.path.exists(track)
    assert "Kevin MacLeod" in credit and "creativecommons.org" in credit


def test_bundled_assets_exist():
    for path in [CAPTION_FONT, TITLE_FONT, *FOCUS_LINES]:
        assert os.path.exists(path), path
    assert os.path.isdir(video_assembler.BGM_DIR)
