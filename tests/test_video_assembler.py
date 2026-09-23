import subprocess
from unittest.mock import patch

import pytest

from video_assembler import CAPTION_FONT, TITLE_FONT, assemble_video


@patch("video_assembler.subprocess.run")
def test_assemble_video_raises_on_length_mismatch(mock_run, tmp_path):
    with pytest.raises(ValueError, match="일치하지 않음"):
        assemble_video(
            ["문장1", "문장2"], ["a1.mp3"], ["i1.png", "i2.png"], str(tmp_path / "out.mp4")
        )

    mock_run.assert_not_called()


@patch("video_assembler.subprocess.run")
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


@patch("video_assembler.subprocess.run")
def test_assemble_video_uses_color_background_when_image_missing(mock_run, tmp_path):
    assemble_video(["문장1"], ["a1.mp3"], [None], str(tmp_path / "out.mp4"))

    first_call_cmd = mock_run.call_args_list[0].args[0]
    assert "lavfi" in first_call_cmd


@patch("video_assembler.subprocess.run")
def test_assemble_video_writes_caption_to_textfile_with_apostrophe(mock_run, tmp_path):
    # OpenAI's -- an apostrophe that would have broken the old text='...' escaping.
    sentence = "OpenAI's new model"
    out_path = str(tmp_path / "out.mp4")

    assemble_video([sentence], ["a1.mp3"], ["i1.png"], out_path)

    # 12자 줄바꿈 — 줄마다 따로 그려서 각 줄을 가운데 정렬
    assert (tmp_path / "caption_1_0.txt").read_text(encoding="utf-8") == "OpenAI's new"
    assert (tmp_path / "caption_1_1.txt").read_text(encoding="utf-8") == "model"

    first_call_cmd = mock_run.call_args_list[0].args[0]
    vf_arg = first_call_cmd[first_call_cmd.index("-vf") + 1]
    assert "textfile=" in vf_arg
    assert vf_arg.count(f"fontfile='{CAPTION_FONT}'") == 2
    assert "text='" not in vf_arg


@patch("video_assembler.subprocess.run")
def test_assemble_video_prints_stderr_and_reraises_on_ffmpeg_failure(mock_run, tmp_path, capsys):
    mock_run.side_effect = subprocess.CalledProcessError(
        1, ["ffmpeg"], stderr=b"ffmpeg exploded"
    )

    with pytest.raises(subprocess.CalledProcessError):
        assemble_video(["문장1"], ["a1.mp3"], ["i1.png"], str(tmp_path / "out.mp4"))

    assert "ffmpeg exploded" in capsys.readouterr().out


@patch("video_assembler.subprocess.run")
def test_assemble_video_cuts_clip_segment_and_drops_original_audio(mock_run, tmp_path):
    assemble_video(["문장1"], ["a1.mp3"], [("src.mp4", 3.5)], str(tmp_path / "out.mp4"))

    cmd = mock_run.call_args_list[0].args[0]
    assert cmd[cmd.index("-ss") + 1] == "3.5"
    assert cmd[cmd.index("-ss") + 3] == "src.mp4"
    assert "tpad=stop_mode=clone" in cmd[cmd.index("-vf") + 1]
    assert cmd[cmd.index("-map") + 1] == "0:v"


@patch("video_assembler.subprocess.run")
def test_assemble_video_draws_big_title_only_on_first_segment(mock_run, tmp_path):
    assemble_video(
        ["문장1", "문장2"], ["a1.mp3", "a2.mp3"], ["i1.png", "i2.png"],
        str(tmp_path / "out.mp4"), title_lines=["N통째 쓴", "쿠팡필수템"],
    )

    first_vf = mock_run.call_args_list[0].args[0][mock_run.call_args_list[0].args[0].index("-vf") + 1]
    second_vf = mock_run.call_args_list[1].args[0][mock_run.call_args_list[1].args[0].index("-vf") + 1]
    assert TITLE_FONT in first_vf
    assert TITLE_FONT not in second_vf
    assert (tmp_path / "title_1.txt").read_text(encoding="utf-8") == "쿠팡필수템"


def test_font_files_exist():
    import os

    assert os.path.exists(CAPTION_FONT) and os.path.exists(TITLE_FONT)
