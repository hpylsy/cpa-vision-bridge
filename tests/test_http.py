import json
import threading
from urllib.request import Request, urlopen

from vision_bridge.config import normalize_config
from vision_bridge.server import RuntimeConfig, build_server


class FakeUpstreamResponse:
    status_code = 200
    headers = {"Content-Type": "application/json"}

    def iter_content(self, chunk_size=65536):
        yield b'{"ok":true}'


def test_healthz_returns_ok():
    runtime = RuntimeConfig(config=normalize_config({"enabled": True}), upstream_origin="http://upstream.test")
    server = build_server(("127.0.0.1", 0), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/healthz", timeout=5) as response:
            assert response.status == 200
            assert response.read() == b"ok\n"
    finally:
        server.shutdown()
        server.server_close()


def test_http_proxy_forwards_transformed_json_to_mock_upstream(monkeypatch):
    captured = {}

    def fake_request(method, url, headers=None, data=None, stream=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = dict(headers or {})
        captured["body"] = json.loads(data.decode("utf-8"))
        captured["stream"] = stream
        captured["timeout"] = timeout
        return FakeUpstreamResponse()

    def fake_describe(image_url, detail, config, auth_headers):
        return "mock image description"

    import vision_bridge.server as server_module

    monkeypatch.setattr(server_module.requests, "request", fake_request)
    runtime = RuntimeConfig(
        config=normalize_config({"enabled": True}),
        upstream_origin="http://127.0.0.1:8317",
        describe_image=fake_describe,
    )
    server = build_server(("127.0.0.1", 0), runtime)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = {
            "model": "gpt-5.4-mini",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "see"},
                        {"type": "input_image", "image_url": "data:image/png;base64,abc"},
                    ],
                }
            ],
        }
        request = Request(
            f"http://127.0.0.1:{server.server_port}/v1/responses",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer test"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert response.read() == b'{"ok":true}'
    finally:
        server.shutdown()
        server.server_close()

    assert captured["url"] == "http://127.0.0.1:8317/v1/responses"
    assert "mock image description" in json.dumps(captured["body"])
    assert "input_image" not in json.dumps(captured["body"])
