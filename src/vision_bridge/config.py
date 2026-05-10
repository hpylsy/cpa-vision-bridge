from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "upstream_origin": "http://127.0.0.1:8317",
    "listen": {
        "host": "0.0.0.0",
        "port": 8320,
    },
    "vision": {
        "model": "gpt-5.4",
        "reasoning_effort": "low",
        "prompt": (
            "Extract only information visible in the image that may be useful for the next model. "
            "Focus on text, errors, code, file paths, tables, UI state, terminal output, and key objects. "
            "Describe objectively and do not solve the problem."
        ),
    },
    "cache": {
        "path": "/var/cache/cpa-vision-bridge/cache.json",
        "ttl_seconds": 604800,
    },
    "models": {
        "gpt-5.4-mini": {
            "preprocess_images": True,
            "collapse_text_content": True,
            "reasoning_effort_aliases": {
                "xhigh": "max",
            },
        },
        "gpt-5.2": {
            "preprocess_images": True,
            "collapse_text_content": True,
            "reasoning_effort_aliases": {
                "xhigh": "high",
            },
        },
        "gpt-5.5": {
            "preprocess_images": False,
            "collapse_text_content": False,
            "reasoning_effort_aliases": {},
        },
    },
}


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _legacy_to_modern(config: dict[str, Any]) -> dict[str, Any]:
    modern: dict[str, Any] = {}

    if "enabled" in config:
        modern["enabled"] = config["enabled"]
    if "upstream_origin" in config:
        modern["upstream_origin"] = config["upstream_origin"]
    if "vision_model" in config or "reasoning_effort" in config:
        modern["vision"] = {}
        if "vision_model" in config:
            modern["vision"]["model"] = config["vision_model"]
        if "reasoning_effort" in config:
            modern["vision"]["reasoning_effort"] = config["reasoning_effort"]
    if "cache_ttl_seconds" in config:
        modern["cache"] = {"ttl_seconds": config["cache_ttl_seconds"]}

    trigger_models = config.get("trigger_models")
    if isinstance(trigger_models, list):
        models = copy.deepcopy(DEFAULT_CONFIG["models"])
        for model_name, policy in models.items():
            policy["preprocess_images"] = model_name in trigger_models
            policy["collapse_text_content"] = model_name in trigger_models and policy.get("collapse_text_content", False)
        for model_name in trigger_models:
            if model_name not in models:
                models[str(model_name)] = {
                    "preprocess_images": True,
                    "collapse_text_content": True,
                    "reasoning_effort_aliases": {},
                }
        modern["models"] = models

    for key in ("listen", "vision", "cache", "models"):
        if key in config and isinstance(config[key], dict):
            modern[key] = _deep_merge(modern.get(key, {}), config[key])

    return modern


def normalize_config(config: dict[str, Any] | None) -> dict[str, Any]:
    raw = config if isinstance(config, dict) else {}
    modern = _legacy_to_modern(raw)
    normalized = _deep_merge(DEFAULT_CONFIG, modern)

    normalized["enabled"] = bool(normalized.get("enabled"))
    normalized["upstream_origin"] = str(normalized.get("upstream_origin") or DEFAULT_CONFIG["upstream_origin"]).rstrip("/")

    listen = normalized["listen"]
    listen["host"] = str(listen.get("host") or DEFAULT_CONFIG["listen"]["host"])
    listen["port"] = int(listen.get("port") or DEFAULT_CONFIG["listen"]["port"])

    vision = normalized["vision"]
    vision["model"] = str(vision.get("model") or DEFAULT_CONFIG["vision"]["model"])
    vision["reasoning_effort"] = str(vision.get("reasoning_effort") or DEFAULT_CONFIG["vision"]["reasoning_effort"])
    vision["prompt"] = str(vision.get("prompt") or DEFAULT_CONFIG["vision"]["prompt"])

    cache = normalized["cache"]
    cache["path"] = str(cache.get("path") or DEFAULT_CONFIG["cache"]["path"])
    cache["ttl_seconds"] = int(cache.get("ttl_seconds") or DEFAULT_CONFIG["cache"]["ttl_seconds"])

    models = normalized.get("models")
    if not isinstance(models, dict):
        normalized["models"] = copy.deepcopy(DEFAULT_CONFIG["models"])
    for model_name, policy in list(normalized["models"].items()):
        if not isinstance(policy, dict):
            normalized["models"][model_name] = {}
            policy = normalized["models"][model_name]
        policy["preprocess_images"] = bool(policy.get("preprocess_images", False))
        policy["collapse_text_content"] = bool(policy.get("collapse_text_content", False))
        aliases = policy.get("reasoning_effort_aliases")
        if not isinstance(aliases, dict):
            policy["reasoning_effort_aliases"] = {}

    return normalized


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - exercised by deployment, not unit tests
            raise RuntimeError("PyYAML is required to read YAML config files") from exc
        loaded = yaml.safe_load(text) or {}
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError("Vision Bridge config must be an object")
    return loaded


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    configured = (
        path
        or os.getenv("VISION_BRIDGE_CONFIG")
        or os.getenv("VISION_PREPROCESS_CONFIG_PATH")
        or ""
    )
    if not configured:
        return normalize_config(DEFAULT_CONFIG)

    config_path = Path(configured)
    if not config_path.exists():
        return normalize_config(DEFAULT_CONFIG)
    return normalize_config(_load_yaml_or_json(config_path))


def runtime_settings(config: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_config(config)
    return {
        "listen_host": os.getenv("VISION_BRIDGE_LISTEN_HOST")
        or os.getenv("VISION_PREPROCESS_LISTEN_HOST")
        or normalized["listen"]["host"],
        "listen_port": int(
            os.getenv("VISION_BRIDGE_LISTEN_PORT")
            or os.getenv("VISION_PREPROCESS_LISTEN_PORT")
            or normalized["listen"]["port"]
        ),
        "upstream_origin": (
            os.getenv("VISION_BRIDGE_UPSTREAM_ORIGIN")
            or os.getenv("VISION_PREPROCESS_UPSTREAM_ORIGIN")
            or normalized["upstream_origin"]
        ).rstrip("/"),
        "cache_path": os.getenv("VISION_BRIDGE_CACHE_PATH")
        or os.getenv("VISION_PREPROCESS_CACHE_PATH")
        or normalized["cache"]["path"],
        "connect_timeout": float(
            os.getenv("VISION_BRIDGE_CONNECT_TIMEOUT")
            or os.getenv("VISION_PREPROCESS_CONNECT_TIMEOUT")
            or 10
        ),
        "read_timeout": float(
            os.getenv("VISION_BRIDGE_READ_TIMEOUT")
            or os.getenv("VISION_PREPROCESS_READ_TIMEOUT")
            or 600
        ),
    }
