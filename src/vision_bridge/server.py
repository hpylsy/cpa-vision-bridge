from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

import requests

from vision_bridge.cache import JsonCache
from vision_bridge.config import load_config, runtime_settings
from vision_bridge.payloads import transform_request_body
from vision_bridge.upstream import describe_image_with_upstream


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


DescribeWithContext = Callable[[str, str, dict[str, Any], dict[str, str]], str]


@dataclass
class RuntimeConfig:
    config: dict[str, Any]
    upstream_origin: str
    connect_timeout: float = 10
    read_timeout: float = 600
    cache: JsonCache | None = None
    describe_image: DescribeWithContext | None = None


class VisionBridgeServer(ThreadingHTTPServer):
    request_queue_size = 128
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass, runtime: RuntimeConfig):
        super().__init__(server_address, RequestHandlerClass)
        self.runtime = runtime


class VisionBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"[vision-bridge] {self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self):
        if self.path == "/healthz":
            payload = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.proxy_request()

    def do_POST(self):
        self.proxy_request()

    def do_PUT(self):
        self.proxy_request()

    def do_PATCH(self):
        self.proxy_request()

    def do_DELETE(self):
        self.proxy_request()

    @property
    def runtime(self) -> RuntimeConfig:
        return self.server.runtime

    def _describe_image(self, image_url: str, detail: str, auth_headers: dict[str, str]) -> str:
        if self.runtime.describe_image:
            return self.runtime.describe_image(image_url, detail, self.runtime.config, auth_headers)
        return describe_image_with_upstream(
            image_url,
            detail,
            self.runtime.config,
            self.runtime.upstream_origin,
            auth_headers,
            cache=self.runtime.cache,
            timeout=(self.runtime.connect_timeout, self.runtime.read_timeout),
        )

    def _transform_json_body(self, body_bytes: bytes, headers: dict[str, str]) -> tuple[bytes, bool]:
        if not body_bytes or self.path.split("?", 1)[0] not in {"/v1/responses", "/v1/chat/completions"}:
            return body_bytes, False
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return body_bytes, False
        if not isinstance(body, dict):
            return body_bytes, False

        transformed, result = transform_request_body(
            self.path,
            body,
            self.runtime.config,
            lambda image_url, detail: self._describe_image(image_url, detail, headers),
        )
        if not result.changed:
            return body_bytes, False
        return json.dumps(transformed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), True

    def proxy_request(self):
        content_length = int(self.headers.get("Content-Length") or 0)
        body_bytes = self.rfile.read(content_length) if content_length else b""
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }

        body_bytes, changed = self._transform_json_body(body_bytes, dict(self.headers.items()))
        if changed:
            headers["Content-Type"] = "application/json"

        try:
            upstream = requests.request(
                self.command,
                self.runtime.upstream_origin.rstrip("/") + self.path,
                headers=headers,
                data=body_bytes if body_bytes else None,
                stream=True,
                timeout=(self.runtime.connect_timeout, self.runtime.read_timeout),
            )
            self.send_response(upstream.status_code)
            for key, value in upstream.headers.items():
                lower_key = key.lower()
                if lower_key in HOP_BY_HOP_HEADERS or lower_key in {"content-encoding", "content-length"}:
                    continue
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in upstream.iter_content(chunk_size=65536):
                if chunk:
                    self.wfile.write(chunk)
            self.close_connection = True
        except Exception as exc:
            payload = json.dumps({"error": {"message": str(exc), "type": "vision_bridge_proxy_error"}}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


def build_server(address: tuple[str, int], runtime: RuntimeConfig) -> VisionBridgeServer:
    return VisionBridgeServer(address, VisionBridgeHandler, runtime)


def main() -> None:
    config = load_config()
    settings = runtime_settings(config)
    cache = JsonCache(settings["cache_path"], int(config["cache"]["ttl_seconds"]))
    runtime = RuntimeConfig(
        config=config,
        upstream_origin=settings["upstream_origin"],
        connect_timeout=settings["connect_timeout"],
        read_timeout=settings["read_timeout"],
        cache=cache,
    )
    server = build_server((settings["listen_host"], settings["listen_port"]), runtime)
    print(
        f"[vision-bridge] listening on {settings['listen_host']}:{settings['listen_port']}, "
        f"upstream={settings['upstream_origin']}",
        flush=True,
    )
    server.serve_forever()
