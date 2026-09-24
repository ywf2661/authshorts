from unittest.mock import patch

import pytest

import script_writer
from config import Settings
from script_writer import ScriptRejected, check_top_script, write_clip_script, write_top_script

TOPIC = "3만원 이하 방한템"
PRODUCTS = [
    {"productName": "난방텐트", "productUrl": "http://a", "point": "침대 위에 치는 텐트형, 체감 온도 올려줌"},
    {"productName": "극세사 담요", "productUrl": "http://b", "point": "리뷰 3만 개, 세탁기 가능"},
    {"productName": "문풍지", "productUrl": "http://c", "point": "창틀 외풍 차단, 붙이기만 하면 됨"},
]
JPEG = b"\xff\xd8\xff\xe0 fake"


def _settings():
    return Settings("ak", "gcid", "gcs", "yrt", "chan123", "https://t.me/x")


def _beat(kind, product, rank, text):
    return {"kind": kind, "product": product, "rank": rank, "text": text}


def _good_script():
    return {
        "title": "3만원 이하 방한템 TOP3",
        "hook_lines": ["안 쓰면", "고생하는 방한템"],
        "labels": ["난방텐트", "극세사 담요", "문풍지"],
        "beats": [
            _beat("hook", 0, 0, "올겨울 *이거* 없으면 진짜 고생해요"),
            _beat("item", 2, 3, "3위는 *문풍지*예요"),
            _beat("item", 2, 3, "창틀에 붙이기만 하면 *외풍*이 막혀요"),
            _beat("item", 1, 2, "2위는 *극세사 담요*"),
            _beat("item", 1, 2, "세탁기에 막 돌려도 되는 담요예요"),
            _beat("reveal", 0, 1, "대망의 1위는 *난방텐트*"),
            _beat("reveal", 0, 1, "침대 위에 치는 텐트라서 포근해요"),
            _beat("reveal", 0, 1, "자는 동안 *체감 온도*가 확 올라가요"),
            _beat("reveal", 0, 1, "한번 쓰면 겨울 내내 못 치워요"),
            _beat("outro", 0, 0, "여러분 겨울 1위 템은 뭐예요?"),
        ],
        "keywords": ["방한템", "자취템"],
    }


def test_good_script_passes():
    assert check_top_script(_good_script(), PRODUCTS, TOPIC) == []


@pytest.mark.parametrize("text, reason", [
    ("제가 써봤는데 따뜻해요", "1인칭"),
    ("요즘 *품절* 대란이에요", "근거"),
    ("전기료 30% 아껴줘요", "근거"),
    ("단돈 9,900원이에요", "가격"),
])
def test_rule_violations_are_reported(text, reason):
    script = _good_script()
    script["beats"][6]["text"] = text

    problems = check_top_script(script, PRODUCTS, TOPIC)

    assert any(reason in p for p in problems), problems


def test_claim_backed_by_point_and_price_in_topic_are_allowed():
    products = [dict(p) for p in PRODUCTS]
    products[0]["point"] = "전기료 절감, 품절 대란"
    script = _good_script()
    script["beats"][6]["text"] = "품절 대란에 *절감*까지"
    script["beats"][0]["text"] = "3만원 이하로 겨울 준비 끝"

    problems = check_top_script(script, products, TOPIC)
    assert not [p for p in problems if "근거" in p or "가격" in p], problems


def test_structure_errors_are_reported():
    script = _good_script()
    script["beats"][1]["product"] = 7  # 범위 밖
    script["beats"][3]["rank"] = 3  # 1번 상품은 2위
    script["beats"][0]["text"] = "난방텐트 하나면 끝"  # 상품명으로 시작하는 훅
    script["labels"] = ["하나"]

    problems = "\n".join(check_top_script(script, PRODUCTS, TOPIC))

    assert "범위 밖" in problems
    assert "순위는 2위" in problems
    assert "상품명으로 시작" in problems
    assert "labels" in problems


def test_total_length_is_checked():
    script = _good_script()
    script["beats"] = script["beats"][:2] + script["beats"][5:6] + script["beats"][-1:]

    assert any("전체 대사" in p for p in check_top_script(script, PRODUCTS, TOPIC))


@patch("script_writer._ask_claude")
def test_write_top_script_retries_once_with_reasons(ask):
    bad = _good_script()
    bad["beats"][6]["text"] = "제가 써봤어요"
    ask.side_effect = [bad, _good_script()]

    result = write_top_script(_settings(), TOPIC, PRODUCTS, [JPEG, JPEG, JPEG], "quiz")

    assert result == _good_script()
    first_content = ask.call_args_list[0].args[1]
    assert first_content[1]["type"] == "image"  # 상품 사진을 함께 보낸다
    assert "1위 맞혀보세요" in first_content[-1]["text"]
    assert "1인칭" in ask.call_args_list[1].args[1][-1]["text"]


@patch("script_writer._ask_claude")
def test_write_top_script_gives_up_after_second_failure(ask):
    bad = _good_script()
    bad["beats"][6]["text"] = "제가 써봤어요"
    ask.return_value = bad

    with pytest.raises(ScriptRejected, match="1인칭"):
        write_top_script(_settings(), TOPIC, PRODUCTS, [JPEG], "result")
    assert ask.call_count == 2


@patch("script_writer._ask_claude")
def test_write_clip_script_validates_start_range(ask):
    ask.return_value = {"title": "t", "hook_lines": ["훅"], "keywords": [],
                        "segments": [{"start": 0, "text": "첫 장면"}, {"start": 99, "text": "끝"}]}

    with pytest.raises(ValueError, match="범위"):
        write_clip_script(_settings(), {"productName": "케이스"}, [(0.0, JPEG)], 10.0)


def test_ask_claude_uses_sonnet_with_json_schema():
    with patch("script_writer.anthropic.Anthropic") as client_cls:
        create = client_cls.return_value.messages.create
        block = type("B", (), {"type": "text", "text": '{"a": 1}'})()
        create.return_value = type("R", (), {"stop_reason": "end_turn", "content": [block]})()

        assert script_writer._ask_claude(_settings(), "hi", {"type": "object"}) == {"a": 1}
        kwargs = create.call_args.kwargs
        assert kwargs["model"] == "claude-sonnet-5"
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        assert kwargs["messages"][-1]["role"] == "user"  # 선채움(prefill) 없음
