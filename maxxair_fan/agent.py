"""HTTP edge agent for remote Pi hardware access."""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from maxxair_fan import config
from maxxair_fan.backends import build_backends
from maxxair_fan.backends.protocols import IRBackend, SensorBackend

logger = logging.getLogger(__name__)


class AgentContext:
    """Shared state for the agent HTTP handler."""

    def __init__(
        self,
        sensor_be: SensorBackend | None = None,
        ir_be: IRBackend | None = None,
        agent_token: str | None = None,
    ) -> None:
        if sensor_be is None or ir_be is None:
            built_sensor, built_ir, _ = build_backends(dedupe_ir=False)
            sensor_be = sensor_be or built_sensor
            ir_be = ir_be or built_ir
        self.sensor_be = sensor_be
        self.ir_be = ir_be
        self.agent_token = agent_token if agent_token is not None else config.AGENT_TOKEN


def _make_handler(context: AgentContext):
    class AgentHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("Agent %s - %s", self.address_string(), format % args)

        def _authorized(self) -> bool:
            if not context.agent_token:
                return True
            auth = self.headers.get("Authorization", "")
            expected = f"Bearer {context.agent_token}"
            return auth == expected

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any] | None:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return {}
            try:
                raw = self.rfile.read(length)
                data = json.loads(raw)
                return data if isinstance(data, dict) else None
            except (json.JSONDecodeError, ValueError):
                return None

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._send_json(200, {"ok": True})
                return

            if self.path != "/temp":
                self._send_json(404, {"error": "not found"})
                return

            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return

            temp = context.sensor_be.read_temp_f()
            if temp is None:
                self._send_json(503, {"error": "sensor read failed"})
                return
            self._send_json(200, {"temp_f": temp})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/ir":
                self._send_json(404, {"error": "not found"})
                return

            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return

            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid JSON body"})
                return

            filename = body.get("filename")
            if not filename or not isinstance(filename, str):
                self._send_json(400, {"error": "filename required"})
                return

            ok = context.ir_be.send(filename)
            if ok:
                self._send_json(200, {"ok": True, "filename": filename})
            else:
                self._send_json(500, {"error": f"IR send failed for {filename}"})

    return AgentHandler


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class AgentServer:
    def __init__(
        self,
        bind: str | None = None,
        port: int | None = None,
        context: AgentContext | None = None,
    ) -> None:
        self.bind = bind if bind is not None else config.AGENT_BIND
        self.port = port if port is not None else config.AGENT_PORT
        self.context = context or AgentContext()
        self._server: ReusableThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, background: bool = False) -> None:
        handler = _make_handler(self.context)
        self._server = ReusableThreadingHTTPServer((self.bind, self.port), handler)
        logger.info("Agent listening on http://%s:%s", self.bind, self.port)

        if background:
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            return

        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("Agent server is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}"


def run_agent(
    *,
    bind: str | None = None,
    port: int | None = None,
    sensor_be: SensorBackend | None = None,
    ir_be: IRBackend | None = None,
    background: bool = False,
) -> AgentServer:
    context = AgentContext(sensor_be=sensor_be, ir_be=ir_be)
    server = AgentServer(bind=bind, port=port, context=context)
    server.start(background=background)
    return server
