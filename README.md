# CPA Vision Bridge

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

CPA Vision Bridge is a lightweight OpenAI-compatible reverse proxy that sits between clients and [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) (CPA/CPAP).

It solves a specific problem: when users send **images** to text-only models (e.g. `gpt-5.4-mini` -> DeepSeek, `gpt-5.2` -> MiniMax), these upstreams cannot process image payloads. Bridge calls a vision-capable model first to convert images into text descriptions, then forwards the pure-text request to CPA.

```
Client --> Vision Bridge :8320 --> CPA/CPAP :8317 --> Provider
                |
                +-- image? --> Vision Model (gpt-5.4) --> text description
```

## Features

- **Image preprocessing**: Detects images in requests, calls a vision model to produce text descriptions
- **Per-model policy**: Configure which models need preprocessing; unconfigured models pass through
- **Reasoning effort mapping**: `xhigh` auto-maps to upstream-supported values (`max`/`high`)
- **Text content collapsing**: Merges multi-part text content into a single string for better upstream compatibility
- **Image description caching**: Same image is not re-processed within 7 days (configurable TTL)
- **Transparent proxy**: Non-trigger models are forwarded as-is, including streaming responses
- **Supports both `/v1/responses` and `/v1/chat/completions`** API formats

## Quick Start

### Install

```bash
git clone https://github.com/hpylsy/cpa-vision-bridge.git
cd cpa-vision-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
enabled: true
upstream_origin: http://127.0.0.1:8317  # CPA address

listen:
  host: 0.0.0.0
  port: 8320

vision:
  model: gpt-5.4           # Vision model for image description
  reasoning_effort: low    # Reasoning intensity for vision model
  prompt: >-               # Prompt sent to vision model
    Extract only information visible in the image that may be useful for the next model.
    Focus on text, errors, code, file paths, tables, UI state, terminal output, and key objects.
    Describe objectively and do not solve the problem.

cache:
  path: /var/cache/cpa-vision-bridge/cache.json
  ttl_seconds: 604800      # Cache for 7 days

models:
  gpt-5.4-mini:            # Model that needs image preprocessing
    preprocess_images: true
    collapse_text_content: true
    reasoning_effort_aliases:
      xhigh: max

  gpt-5.2:
    preprocess_images: true
    collapse_text_content: true
    reasoning_effort_aliases:
      xhigh: high

  gpt-5.5:                 # Pass through directly
    preprocess_images: false
    collapse_text_content: false
    reasoning_effort_aliases: {}
```

### Run

```bash
VISION_BRIDGE_CONFIG=\$PWD/config.yaml python -m vision_bridge
```

### Verify

```bash
# Health check
curl http://127.0.0.1:8320/healthz

# Models (passthrough)
curl http://127.0.0.1:8320/v1/models -H "Authorization: Bearer YOUR_KEY"
```

## Configuration Reference

### `vision` section

| Field | Description | Default |
|-------|-------------|---------|
| `model` | Vision model name (must be supported by CPA) | `gpt-5.4` |
| `reasoning_effort` | Vision model reasoning intensity (`low`/`medium`/`high`) | `low` |
| `prompt` | System prompt sent to vision model | See example above |

### `models` section

Each model name maps to a policy:

| Field | Description |
|-------|-------------|
| `preprocess_images` | `true` = call vision model for images; `false` = passthrough |
| `collapse_text_content` | `true` = merge content list into single string |
| `reasoning_effort_aliases` | Map client values to upstream values, e.g. `xhigh: max` |

**Models not listed in `models` section are passed through by default.**

### Adding a new model

```yaml
models:
  your-model-name:
    preprocess_images: true
    collapse_text_content: true
    reasoning_effort_aliases:
      xhigh: high
```

### Changing the vision model

```yaml
vision:
  model: gpt-5.4              # Codex vision model (default)
  # model: gemini-3-flash     # Or use Gemini
  # model: kiro-claude-sonnet-4-5  # Or use Kiro Claude
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VISION_BRIDGE_CONFIG` | Config file path | - |
| `VISION_BRIDGE_LISTEN_HOST` | Listen address | `0.0.0.0` |
| `VISION_BRIDGE_LISTEN_PORT` | Listen port | `8320` |
| `VISION_BRIDGE_UPSTREAM_ORIGIN` | CPA upstream URL | `http://127.0.0.1:8317` |
| `VISION_BRIDGE_CACHE_PATH` | Cache file path | - |
| `VISION_BRIDGE_CONNECT_TIMEOUT` | Connect timeout (seconds) | `10` |
| `VISION_BRIDGE_READ_TIMEOUT` | Read timeout (seconds) | `600` |

## Deployment

### systemd

```bash
sudo cp systemd/vision-bridge.service.example /etc/systemd/system/vision-bridge.service
# Edit WorkingDirectory, ExecStart, environment variables
sudo systemctl daemon-reload
sudo systemctl enable --now vision-bridge
```

### Docker

```bash
cp config.example.yaml config.yaml
docker compose -f docker-compose.example.yml up --build -d
```

## How It Works

1. Client sends request to Bridge (`:8320`)
2. Bridge checks if the request model is configured with `preprocess_images: true`
3. **If preprocessing needed**:
   - Extract images from request (`image_url` / `input_image` types)
   - Call vision model (via CPA `/v1/responses`) to get text description
   - Replace original images with text descriptions
   - Forward modified pure-text request to CPA
4. **If no preprocessing needed**: Forward request to CPA as-is
5. CPA response is returned to client unchanged (streaming supported)

## Architecture

```
+-------------+     +------------------+     +-------------+
|   Client    |---->|  Vision Bridge   |---->|  CPA/CPAP   |--> Provider
|  (IDE/CLI)  |<----|    :8320         |<----|   :8317     |<-- (Codex/Gemini/...)
+-------------+     +------------------+     +-------------+
                           |
                           | image preprocessing
                           v
                    +-------------+
                    |  CPA/CPAP   |--> Vision Model (gpt-5.4)
                    |   :8317     |
                    +-------------+
```

- **CPA/CPAP**: Core proxy managing all provider auth and routing
- **Vision Bridge**: Optional frontend proxy handling image preprocessing only
- Clients can connect directly to CPA (`:8317`) or through Bridge (`:8320`) for image support

## Tests

```bash
pip install -e .[test]
python -m pytest
```

## License

MIT
