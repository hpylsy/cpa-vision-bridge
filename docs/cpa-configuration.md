# CPA Configuration Guide

这份配置说明面向 CliProxyAPI/CPA。目标是让用户清楚地区分“用户看到的 model alias”和“真实上游 model”，并知道哪些请求应该先经过 Vision Bridge。

## Ports

推荐默认端口：

```text
Vision Bridge: 8320
CPA:           8317
```

客户端使用：

```text
http://127.0.0.1:8320/v1
```

Vision Bridge 转发到：

```text
http://127.0.0.1:8317
```

## Alias Example

下面是脱敏后的 CPA YAML 片段。不要把真实 API key 放进开源仓库。

```yaml
host: ""
port: 8317

openai-compatibility:
  - name: Nvidia
    base-url: https://integrate.api.nvidia.com/v1
    api-key-entries:
      - api-key: REDACTED
    models:
      - name: deepseek-ai/deepseek-v4-pro
        alias: gpt-5.4-mini
      - name: minimaxai/minimax-m2.7
        alias: gpt-5.2
```

含义：

- 用户请求 `model: gpt-5.4-mini`。
- Vision Bridge 看到这是 DeepSeek alias，先处理图片和 payload 兼容。
- CPA 收到仍然是 `gpt-5.4-mini` 的请求。
- CPA 根据 alias 把它路由到 `deepseek-ai/deepseek-v4-pro`。

`gpt-5.2` 同理，CPA 会把它路由到 `minimaxai/minimax-m2.7`。

## Reasoning Effort Override

部分 vLLM/SGLang/OpenAI-compatible 上游不接受 `xhigh`。可以让 Bridge 先做兼容，也可以在 CPA 里加兜底 override。

```yaml
payload:
  override:
    - models:
        - name: "gpt-5.4-mini"
          protocol: "openai"
        - name: "deepseek-ai/deepseek-v4-pro"
          protocol: "openai"
      params:
        "reasoning.effort": "max"
        "reasoning_effort": "max"
    - models:
        - name: "gpt-5.2"
          protocol: "openai"
        - name: "minimaxai/minimax-m2.7"
          protocol: "openai"
      params:
        "reasoning.effort": "high"
        "reasoning_effort": "high"
```

## Which Models Need Bridge

默认需要 Vision Bridge：

- `gpt-5.4-mini` -> DeepSeek route
- `gpt-5.2` -> MiniMax route

默认直接透传：

- `gpt-5.5`
- 没有显式配置 `preprocess_images: true` 的模型

原则很简单：只有最终会到 DeepSeek / MiniMax 这类文本模型、但用户可能发送图片的 route 才需要预处理。不要把所有模型都强行绕一遍 Bridge。
