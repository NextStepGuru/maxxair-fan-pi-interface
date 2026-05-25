import argparse
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from maxxair_fan.backends.in_memory_firebase import InMemoryFirebaseBackend

logger = logging.getLogger(__name__)

DEFAULT_STATE = {
    "fans": {
        "fan1": {
            "targetTemp": 72.0,
            "direction": "in",
        }
    }
}

HTML_FORM = """<!DOCTYPE html>
<html>
<head><title>Fake Firebase RTDB</title></head>
<body>
  <h1>Fake Firebase — fans/fan1</h1>
  <form method="POST" action="/fans/fan1.json">
    <label>Target temp (°F):
      <input name="targetTemp" type="number" step="0.1" value="{target}">
    </label><br>
    <label>Direction:
      <select name="direction">
        <option value="in"{in_sel}>in</option>
        <option value="out"{out_sel}>out</option>
      </select>
    </label><br>
    <button type="submit">Update</button>
  </form>
  <h2>Current state</h2>
  <pre>{state_json}</pre>
</body>
</html>
"""


class FakeFirebaseServer:
    def __init__(self, state_path: Path, initial_state: dict | None = None) -> None:
        self.state_path = state_path
        self.backend = InMemoryFirebaseBackend(self._load_state(initial_state))

    def _load_state(self, initial_state: dict | None) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not read state file; starting fresh")

        return initial_state or json.loads(json.dumps(DEFAULT_STATE))

    def save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.backend.state, indent=2) + "\n")
        tmp.replace(self.state_path)

    def json_path(self, raw_path: str) -> str:
        path = unquote(raw_path.lstrip("/"))
        if path.endswith(".json"):
            path = path[: -len(".json")]
        return path


def make_handler(server: FakeFirebaseServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FakeFirebase/1.0"

        def log_message(self, format, *args):
            logger.info("%s - %s", self.address_string(), format % args)

        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length) if length else b""

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                fan1 = server.backend.get("fans/fan1") or {}
                target = fan1.get("targetTemp", 72.0)
                direction = fan1.get("direction", "in")
                html = HTML_FORM.format(
                    target=target,
                    in_sel=" selected" if direction == "in" else "",
                    out_sel=" selected" if direction == "out" else "",
                    state_json=json.dumps(server.backend.state, indent=2),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return

            path = server.json_path(parsed.path)
            value = server.backend.get(path)
            if value is None:
                self._send_json(200, None)
            else:
                self._send_json(200, value)

        def do_PATCH(self) -> None:
            self._handle_write("patch")

        def do_PUT(self) -> None:
            self._handle_write("put")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.endswith(".json"):
                content_type = self.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    self._handle_write("patch")
                    return

                body = self._read_body().decode("utf-8")
                fields = parse_qs(body)
                payload = {}
                if "targetTemp" in fields:
                    payload["targetTemp"] = float(fields["targetTemp"][0])
                if "direction" in fields:
                    payload["direction"] = fields["direction"][0]
                path = server.json_path(parsed.path)
                server.backend.patch(path, payload)
                server.save_state()
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
                return

            self._send_json(405, {"error": "method not allowed"})

        def _handle_write(self, mode: str) -> None:
            parsed = urlparse(self.path)
            path = server.json_path(parsed.path)
            raw = self._read_body()
            if not raw:
                self._send_json(400, {"error": "empty body"})
                return

            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(400, {"error": "invalid json"})
                return

            if mode == "put":
                server.backend.put(path, payload)
            else:
                server.backend.patch(path, payload)

            server.save_state()
            self._send_json(200, payload)

    return Handler


def run_server(host: str, port: int, state_path: Path) -> ThreadingHTTPServer:
    server_obj = FakeFirebaseServer(state_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(server_obj))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Fake Firebase RTDB server for local dev")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--state", type=Path, default=Path(".dev/firebase.json"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    httpd = run_server(args.host, args.port, args.state)
    logger.info("Fake Firebase listening on http://%s:%d", args.host, args.port)
    logger.info("State file: %s", args.state.resolve())

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down fake Firebase server")
        httpd.shutdown()


if __name__ == "__main__":
    main()
