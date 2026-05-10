from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable

from vision_bridge.policy import normalize_reasoning_effort, should_collapse_text_content, should_preprocess_images


DescribeImage = Callable[[str, str], str]


@dataclass
class TransformResult:
    changed: bool = False
    reasoning_changed: bool = False
    image_changed: bool = False
    text_content_changed: bool = False


def _image_url_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        url = value.get("url") or value.get("image_url")
        return url if isinstance(url, str) else ""
    return ""


def _image_detail_value(part: dict[str, Any]) -> str:
    detail = part.get("detail")
    if isinstance(detail, str):
        return detail
    image_url = part.get("image_url")
    if isinstance(image_url, dict) and isinstance(image_url.get("detail"), str):
        return image_url["detail"]
    return "high"


def is_responses_image_part(part: Any) -> bool:
    if not isinstance(part, dict):
        return False
    if part.get("type") in {"input_image", "image_url"}:
        return True
    return bool(part.get("image_url")) and part.get("type") != "input_text"


def is_chat_image_part(part: Any) -> bool:
    return isinstance(part, dict) and part.get("type") == "image_url"


def merge_text_parts(parts: list[dict[str, Any]], text_type: str) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            merged.append({"type": text_type, "text": "\n\n".join(pending)})
            pending.clear()

    for part in parts:
        if isinstance(part, dict) and part.get("type") == text_type and isinstance(part.get("text"), str):
            pending.append(part["text"])
        else:
            flush()
            merged.append(part)
    flush()
    return merged


def collapse_text_only_parts(parts: Any, text_type: str) -> Any:
    if not isinstance(parts, list):
        return parts
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != text_type or not isinstance(part.get("text"), str):
            return parts
        text_parts.append(part["text"])
    return "\n\n".join(text_parts)


def format_image_description(description: str, config: dict[str, Any]) -> str:
    vision = config.get("vision") if isinstance(config, dict) else {}
    model = vision.get("model", "vision model") if isinstance(vision, dict) else "vision model"
    effort = vision.get("reasoning_effort", "low") if isinstance(vision, dict) else "low"
    clean = (description or "").strip() or "Image preprocessing did not return a usable description."
    return (
        f"[Image preprocessed by Vision Bridge using {model} ({effort}); "
        "the original image was not forwarded to the target model]\n"
        f"{clean}"
    )


def transform_responses_body(body: dict[str, Any], config: dict[str, Any], describe_image: DescribeImage) -> tuple[bool, bool]:
    if not should_preprocess_images(config, body) and not should_collapse_text_content(config, body):
        return False, False
    if not isinstance(body.get("input"), list):
        return False, False

    image_changed = False
    text_changed = False

    for item in body["input"]:
        if not isinstance(item, dict) or not isinstance(item.get("content"), list):
            continue

        new_parts: list[dict[str, Any]] = []
        for part in item["content"]:
            if should_preprocess_images(config, body) and is_responses_image_part(part):
                image_url = _image_url_value(part.get("image_url") or part.get("url"))
                detail = _image_detail_value(part)
                description = describe_image(image_url, detail)
                new_parts.append({"type": "input_text", "text": format_image_description(description, config)})
                image_changed = True
            else:
                new_parts.append(part)

        new_content: Any = merge_text_parts(new_parts, "input_text") if image_changed else new_parts
        if should_collapse_text_content(config, body):
            collapsed = collapse_text_only_parts(new_content, "input_text")
            if isinstance(collapsed, str):
                new_content = collapsed

        if new_content != item["content"]:
            item["content"] = new_content
            if not image_changed:
                text_changed = True
            else:
                text_changed = text_changed or isinstance(new_content, str)

    return image_changed, text_changed


def transform_chat_completions_body(
    body: dict[str, Any],
    config: dict[str, Any],
    describe_image: DescribeImage,
) -> tuple[bool, bool]:
    if not should_preprocess_images(config, body) and not should_collapse_text_content(config, body):
        return False, False
    if not isinstance(body.get("messages"), list):
        return False, False

    image_changed = False
    text_changed = False

    for message in body["messages"]:
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue

        new_parts: list[dict[str, Any]] = []
        for part in message["content"]:
            if should_preprocess_images(config, body) and is_chat_image_part(part):
                image_url = _image_url_value(part.get("image_url"))
                detail = _image_detail_value(part)
                description = describe_image(image_url, detail)
                new_parts.append({"type": "text", "text": format_image_description(description, config)})
                image_changed = True
            else:
                new_parts.append(part)

        new_content: Any = merge_text_parts(new_parts, "text") if image_changed else new_parts
        if should_collapse_text_content(config, body):
            collapsed = collapse_text_only_parts(new_content, "text")
            if isinstance(collapsed, str):
                new_content = collapsed

        if new_content != message["content"]:
            message["content"] = new_content
            if not image_changed:
                text_changed = True
            else:
                text_changed = text_changed or isinstance(new_content, str)

    return image_changed, text_changed


def transform_request_body(
    path: str,
    body: dict[str, Any],
    config: dict[str, Any],
    describe_image: DescribeImage,
) -> tuple[dict[str, Any], TransformResult]:
    if not isinstance(body, dict) or not config.get("enabled", True):
        return body, TransformResult()

    transformed = copy.deepcopy(body)
    result = TransformResult()
    result.reasoning_changed = normalize_reasoning_effort(transformed, config)

    if path.split("?", 1)[0] == "/v1/responses":
        result.image_changed, result.text_content_changed = transform_responses_body(transformed, config, describe_image)
    elif path.split("?", 1)[0] == "/v1/chat/completions":
        result.image_changed, result.text_content_changed = transform_chat_completions_body(
            transformed,
            config,
            describe_image,
        )

    result.changed = result.reasoning_changed or result.image_changed or result.text_content_changed
    return (transformed if result.changed else body), result


def build_vision_payload(image_url: str, detail: str, config: dict[str, Any]) -> dict[str, Any]:
    vision = config.get("vision") if isinstance(config, dict) else {}
    prompt = vision.get("prompt") if isinstance(vision, dict) else None
    return {
        "model": vision.get("model", "gpt-5.4") if isinstance(vision, dict) else "gpt-5.4",
        "reasoning": {"effort": vision.get("reasoning_effort", "low") if isinstance(vision, dict) else "low"},
        "store": False,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": str(prompt or "")},
                    {"type": "input_image", "image_url": image_url, "detail": detail or "high"},
                ],
            }
        ],
    }


def extract_response_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    texts: list[str] = []
    for output in payload.get("output") or []:
        if not isinstance(output, dict):
            continue
        for content in output.get("content") or []:
            if isinstance(content, dict):
                text = content.get("text") or content.get("output_text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    if texts:
        return "\n".join(texts)

    for choice in payload.get("choices") or []:
        message = choice.get("message") if isinstance(choice, dict) else None
        if isinstance(message, dict) and isinstance(message.get("content"), str):
            return message["content"].strip()

    return ""
