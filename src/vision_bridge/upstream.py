from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests

from vision_bridge.cache import JsonCache
from vision_bridge.payloads import build_vision_payload, extract_response_text


def auth_headers_from(headers: dict[str, str]) -> dict[str, str]:
    selected = {}
    for key, value in headers.items():
        if key.lower() in {"authorization", "x-api-key"}:
            selected[key] = value
    return selected


def describe_image_with_upstream(
    image_url: str,
    detail: str,
    config: dict[str, Any],
    upstream_origin: str,
    headers: dict[str, str],
    cache: JsonCache | None = None,
    timeout: tuple[float, float] = (10, 600),
) -> str:
    if not image_url:
        return "Image part did not include an image URL."

    if cache:
        cached = cache.get(image_url)
        if cached:
            return cached

    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Vision-Bridge": "1",
    }
    request_headers.update(auth_headers_from(headers))

    try:
        response = requests.post(
            urljoin(upstream_origin.rstrip("/") + "/", "v1/responses"),
            headers=request_headers,
            json=build_vision_payload(image_url, detail, config),
            timeout=timeout,
        )
        response.raise_for_status()
        description = extract_response_text(response.json())
        if not description:
            description = "Image preprocessing completed, but the vision model returned no text."
        if cache:
            cache.set(image_url, description)
        return description
    except Exception as exc:
        return f"Image preprocessing failed: {exc}"
