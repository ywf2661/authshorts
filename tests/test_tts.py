from unittest.mock import patch

import pytest

import tts


def test_speech_text_adds_pause_between_beats():
    assert tts.speech_text(["3위는 문풍지", "끝이에요!"]) == "3위는 문풍지. 끝이에요!"


def test_timeline_aligns_word_boundaries_to_beats():
    texts = ["올겨울 이거 없으면", "3위는 문풍지예요"]
    words = [(0.1, 0.5, "올겨울"), (0.5, 0.8, "이거"), (0.8, 1.2, "없으면"),
             (1.6, 1.9, "3위는"), (1.9, 2.6, "문풍지예요")]

    beats = tts.timeline(texts, words, 3.0)

    assert beats[0]["start"] == 0.0
    assert beats[0]["end"] == pytest.approx(1.4)  # 1.2와 1.6의 중간
    assert beats[1]["start"] == pytest.approx(1.4)
    assert beats[1]["end"] == 3.0
    assert beats[1]["words"] == [(1.6, 1.9), (1.9, 2.6)]


def test_timeline_tolerates_punctuation_and_split_words():
    texts = ["대망의 1위는, 난방텐트!"]
    words = [(0.0, 0.4, "대망의"), (0.4, 0.6, "1위"), (0.6, 0.8, "는"), (0.9, 1.5, "난방텐트")]

    beats = tts.timeline(texts, words, 2.0)

    assert beats[0]["words"] == [(0.0, 0.4), (0.4, 0.8), (0.9, 1.5)]


def test_timeline_falls_back_to_char_proportional_when_words_mismatch():
    texts = ["가나 다라마바"]
    beats = tts.timeline(texts, [(0.0, 1.0, "전혀다른말")], 6.0)

    assert beats[0]["words"] == [(0.0, 2.0), (2.0, 6.0)]


def test_timeline_without_words_is_proportional():
    beats = tts.timeline(["가나", "다라"], None, 4.0)

    assert [b["start"] for b in beats] == [0.0, 2.0]
    assert beats[-1]["end"] == 4.0


@patch("tts._synthesize_azure")
@patch("tts._synthesize_edge", side_effect=RuntimeError("edge 막힘"))
def test_synthesize_falls_back_to_azure_without_timings(edge, azure, tmp_path):
    result = tts.synthesize(["안녕"], str(tmp_path / "n.mp3"), "key", "koreacentral")

    assert result is None
    azure.assert_called_once()


@patch("tts._synthesize_edge", side_effect=RuntimeError("edge 막힘"))
def test_synthesize_raises_without_azure_key(edge, tmp_path):
    with pytest.raises(RuntimeError):
        tts.synthesize(["안녕"], str(tmp_path / "n.mp3"))
