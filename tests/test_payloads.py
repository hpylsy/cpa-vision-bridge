import copy
import json
from pathlib import Path

from vision_bridge.config import DEFAULT_CONFIG, normalize_config
from vision_bridge.payloads import build_vision_payload, extract_response_text, transform_request_body


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)


def describe_image(image_url, detail):
    return f"描述 {image_url} detail={detail}"


def test_responses_text_only_content_list_collapses_for_minimax_alias():
    body = load_fixture("responses_text_list.json")
    transformed, result = transform_request_body("/v1/responses", body, normalize_config(DEFAULT_CONFIG), describe_image)

    assert result.changed is True
    assert result.reasoning_changed is True
    assert result.text_content_changed is True
    assert transformed["reasoning"]["effort"] == "high"
    assert transformed["input"][0]["content"] == "第一段\n\n第二段"


def test_responses_image_is_replaced_and_not_forwarded_to_text_model():
    body = load_fixture("responses_with_image.json")
    transformed, result = transform_request_body("/v1/responses", body, normalize_config(DEFAULT_CONFIG), describe_image)
    payload_text = json.dumps(transformed, ensure_ascii=False)

    assert result.changed is True
    assert result.image_changed is True
    assert transformed["reasoning_effort"] == "max"
    assert "描述 data:image/png;base64,abc detail=high" in payload_text
    assert "input_image" not in payload_text
    assert "image_url" not in payload_text


def test_non_trigger_model_is_passthrough():
    body = {
        "model": "gpt-5.5",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "data:image/png;base64,abc"}
                ],
            }
        ],
    }
    original = copy.deepcopy(body)
    calls = []

    transformed, result = transform_request_body(
        "/v1/responses",
        body,
        normalize_config(DEFAULT_CONFIG),
        lambda image_url, detail: calls.append((image_url, detail)) or "unused",
    )

    assert result.changed is False
    assert transformed == original
    assert calls == []


def test_chat_completions_image_parts_become_text_content():
    body = load_fixture("chat_with_image.json")
    transformed, result = transform_request_body("/v1/chat/completions", body, normalize_config(DEFAULT_CONFIG), describe_image)
    payload_text = json.dumps(transformed, ensure_ascii=False)

    assert result.changed is True
    assert result.image_changed is True
    assert transformed["messages"][0]["content"].startswith("请识别图里有什么")
    assert "https://example.test/screenshot.png" in transformed["messages"][0]["content"]
    assert "image_url" not in payload_text


def test_build_vision_payload_uses_low_reasoning_vision_model():
    payload = build_vision_payload("https://example.test/a.png", "low", normalize_config(DEFAULT_CONFIG))

    assert payload["model"] == "gpt-5.4"
    assert payload["reasoning"]["effort"] == "low"
    assert payload["input"][0]["content"][1]["type"] == "input_image"


def test_extract_response_text_handles_responses_and_chat_shapes():
    assert extract_response_text({"output_text": "hello"}) == "hello"
    assert (
        extract_response_text(
            {
                "output": [
                    {"content": [{"type": "output_text", "text": "a"}, {"type": "output_text", "text": "b"}]}
                ]
            }
        )
        == "a\nb"
    )
    assert extract_response_text({"choices": [{"message": {"content": "chat"}}]}) == "chat"
