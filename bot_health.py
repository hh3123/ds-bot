"""Крошечный HTTP-ответчик, чтобы облачный хост видел: процесс жив.

Нужен для HuggingFace Spaces/Render: стучит пингер (UptimeRobot и т.п.),
хост не усыпляет контейнер. Слушаем порт из HEALTH_PORT (HF: 7860).
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("бот жив".encode("utf-8"))

    def log_message(self, *args) -> None:  # тишина в логах
        pass


def maybe_start_health_server() -> None:
    port = int(os.getenv("HEALTH_PORT", "0"))
    if not port:
        return
    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True, name="health-http").start()
