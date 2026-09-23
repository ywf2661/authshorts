import os
from unittest.mock import AsyncMock, patch

import pytest

from tts import synthesize


@patch("tts._synthesize_one", new_callable=AsyncMock)
def test_synthesize_creates_one_path_per_sentence(mock_synth, tmp_path):
    paths = synthesize(["문장1", "문장2"], str(tmp_path))

    assert paths == [
        str(tmp_path / "1.mp3"),
        str(tmp_path / "2.mp3"),
    ]
    assert mock_synth.call_count == 2
    mock_synth.assert_any_call("문장1", str(tmp_path / "1.mp3"), "ko-KR-SunHiNeural")
    mock_synth.assert_any_call("문장2", str(tmp_path / "2.mp3"), "ko-KR-SunHiNeural")


@patch("tts._synthesize_one", new_callable=AsyncMock)
def test_synthesize_propagates_errors(mock_synth, tmp_path):
    mock_synth.side_effect = RuntimeError("network down")

    with pytest.raises(RuntimeError):
        synthesize(["문장1"], str(tmp_path))


@patch("tts._synthesize_one", new_callable=AsyncMock)
def test_synthesize_creates_out_dir(mock_synth, tmp_path):
    out_dir = tmp_path / "nested" / "dir"

    synthesize(["문장1"], str(out_dir))

    assert os.path.isdir(out_dir)
