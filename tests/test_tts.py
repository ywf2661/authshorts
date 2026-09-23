import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tts import DEFAULT_VOICE, synthesize


def test_default_voice_is_hyunsu():
    assert DEFAULT_VOICE == "ko-KR-HyunsuMultilingualNeural"


@patch("tts._synthesize_one", new_callable=AsyncMock)
def test_synthesize_uses_edge_tts_without_azure_key(mock_synth, tmp_path):
    paths = synthesize(["문장1", "문장2"], str(tmp_path))

    assert paths == [str(tmp_path / "1.mp3"), str(tmp_path / "2.mp3")]
    mock_synth.assert_any_call("문장1", str(tmp_path / "1.mp3"), DEFAULT_VOICE)
    mock_synth.assert_any_call("문장2", str(tmp_path / "2.mp3"), DEFAULT_VOICE)


@patch("tts._synthesize_one", new_callable=AsyncMock)
@patch("tts.requests.post")
def test_synthesize_uses_azure_when_key_present(mock_post, mock_edge, tmp_path):
    mock_post.return_value = MagicMock(ok=True, content=b"mp3")

    paths = synthesize(["A&B <좋아요>"], str(tmp_path), "key", "koreacentral")

    assert (tmp_path / "1.mp3").read_bytes() == b"mp3"
    mock_edge.assert_not_called()
    assert mock_post.call_args.args[0] == "https://koreacentral.tts.speech.microsoft.com/cognitiveservices/v1"
    ssml = mock_post.call_args.kwargs["data"].decode("utf-8")
    assert DEFAULT_VOICE in ssml
    assert "A&amp;B &lt;좋아요&gt;" in ssml  # SSML 특수문자 이스케이프
    assert paths == [str(tmp_path / "1.mp3")]


@patch("tts._synthesize_one", new_callable=AsyncMock)
@patch("tts.requests.post")
def test_synthesize_falls_back_to_edge_when_azure_fails(mock_post, mock_edge, tmp_path):
    mock_post.return_value = MagicMock(ok=False, status_code=401, text="unauthorized")

    synthesize(["문장1"], str(tmp_path), "bad", "koreacentral")

    mock_edge.assert_called_once_with("문장1", str(tmp_path / "1.mp3"), DEFAULT_VOICE)


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
