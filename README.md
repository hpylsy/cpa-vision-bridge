# CPA Vision Bridge

CPA Vision Bridge 是一个放在客户端和 CliProxyAPI/CPA 之间的小型 OpenAI-compatible 代理。它解决的问题很具体：当用户把图片发给 `gpt-5.4-mini` 或 `gpt-5.2` 这类公开 alias 时，CPA 最终会把请求转给 DeepSeek / MiniMax 风格的文本模型，而这些上游不一定接受原始图片 payload。Bridge 会先调用一个真正有视觉能力的模型把图片转成客观文本描述，再把纯文本上下文发给 CPA。

参考链路：

```text
Client -> CPA Vision Bridge :8320 -> CliProxyAPI/CPA :8317 -> Provider
```

默认策略只处理两条需要图片预处理的 alias：

- `gpt-5.4-mini`：CPA alias 到 `deepseek-ai/deepseek-v4-pro`
- `gpt-5.2`：CPA alias 到 `minimaxai/minimax-m2.7`

`gpt-5.5` 和其他未配置模型默认直接透传。

## Quick Start

```bash
cd vision-bridge
python3 -m venv .venv
. .venv/bin/activate
pip install -e .[test]
cp config.example.yaml config.yaml
VISION_BRIDGE_CONFIG=$PWD/config.yaml python -m vision_bridge
```

健康检查：

```bash
curl http://127.0.0.1:8320/healthz
```

客户端把 OpenAI-compatible base URL 指到：

```text
http://127.0.0.1:8320/v1
```

CPA 继续监听：

```text
http://127.0.0.1:8317
```

## Environment Variables

新变量：

- `VISION_BRIDGE_CONFIG`：YAML/JSON 配置路径。
- `VISION_BRIDGE_LISTEN_HOST`：监听地址，默认 `0.0.0.0`。
- `VISION_BRIDGE_LISTEN_PORT`：监听端口，默认 `8320`。
- `VISION_BRIDGE_UPSTREAM_ORIGIN`：CPA 地址，默认 `http://127.0.0.1:8317`。
- `VISION_BRIDGE_CACHE_PATH`：图片描述缓存路径。
- `VISION_BRIDGE_CONNECT_TIMEOUT`：连接超时秒数。
- `VISION_BRIDGE_READ_TIMEOUT`：读取超时秒数。

兼容旧变量一版：

- `VISION_PREPROCESS_CONFIG_PATH`
- `VISION_PREPROCESS_LISTEN_HOST`
- `VISION_PREPROCESS_LISTEN_PORT`
- `VISION_PREPROCESS_UPSTREAM_ORIGIN`
- `VISION_PREPROCESS_CACHE_PATH`
- `VISION_PREPROCESS_CONNECT_TIMEOUT`
- `VISION_PREPROCESS_READ_TIMEOUT`

## What It Changes

- `/v1/responses`：支持 `input_image` / `image_url` 图片块预处理。
- `/v1/chat/completions`：支持 `image_url` 图片块预处理。
- `reasoning.effort=xhigh` / `reasoning_effort=xhigh`：
  - `gpt-5.4-mini` 转为 `max`
  - `gpt-5.2` 转为 `high`
- text-only content list：
  - `gpt-5.4-mini` 与 `gpt-5.2` 会折叠为上游更容易接受的字符串。
- 预处理完成后，发给 CPA 的主模型请求不再包含原始图片。

## Docker

```bash
cp config.example.yaml config.yaml
docker compose -f docker-compose.example.yml up --build
```

如果 CPA 不在宿主机 `8317`，修改 `VISION_BRIDGE_UPSTREAM_ORIGIN`。

## systemd

复制示例：

```bash
sudo cp systemd/vision-bridge.service.example /etc/systemd/system/vision-bridge.service
```

然后按你的部署目录调整：

- `WorkingDirectory`
- `ExecStart`
- `VISION_BRIDGE_CONFIG`
- `VISION_BRIDGE_UPSTREAM_ORIGIN`

## Tests

```bash
python -m pytest
python -m py_compile src/vision_bridge/*.py
```

测试覆盖模型策略、Responses payload、Chat Completions payload、reasoning effort 兼容、非触发模型透传和 HTTP mock upstream。

## More Docs

- [CPA configuration](docs/cpa-configuration.md)
- [Troubleshooting](docs/troubleshooting.md)
