# Troubleshooting

## `multimodal processing is not enabled for this model`

这个错误通常说明原始图片 payload 被发到了不支持图片的上游，例如 DeepSeek / MiniMax 风格的文本模型。

检查顺序：

1. 客户端 base URL 是否指向 Vision Bridge：

   ```text
   http://127.0.0.1:8320/v1
   ```

2. Vision Bridge 是否转发到 CPA：

   ```bash
   curl http://127.0.0.1:8320/healthz
   ```

3. `config.yaml` 里对应 alias 是否开启：

   ```yaml
   models:
     gpt-5.4-mini:
       preprocess_images: true
     gpt-5.2:
       preprocess_images: true
   ```

4. CPA alias 是否正确：

   ```yaml
   deepseek-ai/deepseek-v4-pro -> gpt-5.4-mini
   minimaxai/minimax-m2.7 -> gpt-5.2
   ```

5. 日志里是否能看到请求先打到 `8320`，再到 `8317`。

如果客户端直接连 `8317`，Bridge 没有机会把图片转成文本。

## `reasoning_effort xhigh not accepted`

这个错误说明上游不接受 `xhigh`。默认策略：

- `gpt-5.4-mini`: `xhigh` -> `max`
- `gpt-5.2`: `xhigh` -> `high`

检查：

```yaml
models:
  gpt-5.4-mini:
    reasoning_effort_aliases:
      xhigh: max
  gpt-5.2:
    reasoning_effort_aliases:
      xhigh: high
```

如果你新增了其他模型，需要按对应上游能力添加 alias。

## Text-only Responses content list 失败

有些上游接受字符串内容，但不接受这样的纯文本 list：

```json
[
  {"type": "input_text", "text": "hello"}
]
```

Bridge 默认会对 `gpt-5.4-mini` 和 `gpt-5.2` 折叠为：

```json
"hello"
```

对应配置：

```yaml
collapse_text_content: true
```

## Vision model 没返回描述

Bridge 会把失败信息写成文本并继续发给主模型，避免图片原样穿透到 DeepSeek / MiniMax。你应该检查：

- 预处理 vision model 是否可用。
- `Authorization` 是否从客户端传到了 Bridge。
- CPA 是否允许 Bridge 调用 `vision.model`。
- 图片 URL 是否可被上游访问；`data:` URL 是否过大。

## 最小诊断请求

```bash
curl http://127.0.0.1:8320/v1/responses \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer sk-redacted' \
  -d '{
    "model": "gpt-5.4-mini",
    "reasoning": {"effort": "xhigh"},
    "input": [
      {
        "role": "user",
        "content": [
          {"type": "input_text", "text": "describe this"},
          {"type": "input_image", "image_url": "https://example.com/screenshot.png"}
        ]
      }
    ]
  }'
```

如果它仍然报 multimodal 错误，优先确认请求有没有经过 `8320`。
