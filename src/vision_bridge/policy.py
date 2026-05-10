from __future__ import annotations

from typing import Any


def model_policy(config: dict[str, Any], model_name: str | None) -> dict[str, Any]:
    models = config.get("models") if isinstance(config, dict) else {}
    if not isinstance(models, dict) or not model_name:
        return {}
    policy = models.get(str(model_name))
    return policy if isinstance(policy, dict) else {}


def is_configured_model(config: dict[str, Any], body: dict[str, Any]) -> bool:
    if not isinstance(body, dict):
        return False
    return bool(model_policy(config, body.get("model")))


def should_preprocess_images(config: dict[str, Any], body: dict[str, Any]) -> bool:
    return bool(model_policy(config, body.get("model")).get("preprocess_images"))


def should_collapse_text_content(config: dict[str, Any], body: dict[str, Any]) -> bool:
    return bool(model_policy(config, body.get("model")).get("collapse_text_content"))


def normalize_reasoning_effort(body: dict[str, Any], config: dict[str, Any]) -> bool:
    if not isinstance(body, dict):
        return False

    aliases = model_policy(config, body.get("model")).get("reasoning_effort_aliases") or {}
    if not isinstance(aliases, dict) or not aliases:
        return False

    changed = False
    reasoning = body.get("reasoning")
    if isinstance(reasoning, dict):
        effort = reasoning.get("effort")
        if effort in aliases:
            reasoning["effort"] = aliases[effort]
            changed = True

    effort = body.get("reasoning_effort")
    if effort in aliases:
        body["reasoning_effort"] = aliases[effort]
        changed = True

    return changed
