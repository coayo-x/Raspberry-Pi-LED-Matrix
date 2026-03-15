import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config import DASHBOARD_HOST, DASHBOARD_POLL_INTERVAL_MS, DASHBOARD_PORT, DB_PATH
from current_display_state import load_current_display_state
from runtime_control import request_skip_category

ASSETS_DIR = Path(__file__).with_name("dashboard_assets")
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
    "/dashboard.js": ("dashboard.js", "application/javascript; charset=utf-8"),
}
API_PATH = "/api/current-display-state"
SKIP_CATEGORY_API_PATH = "/api/skip-category"


def _read_asset(filename: str) -> bytes:
    return (ASSETS_DIR / filename).read_bytes()


def create_dashboard_server(
    host: str = DASHBOARD_HOST,
    port: int = DASHBOARD_PORT,
    db_path: str = DB_PATH,
) -> ThreadingHTTPServer:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = self.path.split("?", 1)[0]

            if route == API_PATH:
                body = json.dumps(load_current_display_state(db_path)).encode("utf-8")
                self._send_response(
                    HTTPStatus.OK, "application/json; charset=utf-8", body
                )
                return

            if route in STATIC_ROUTES:
                filename, content_type = STATIC_ROUTES[route]
                body = (
                    _render_html()
                    if filename == "index.html"
                    else _read_asset(filename)
                )
                self._send_response(HTTPStatus.OK, content_type, body)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:
            route = self.path.split("?", 1)[0]

            if route == SKIP_CATEGORY_API_PATH:
                result = request_skip_category(db_path=db_path)
                body = json.dumps(result).encode("utf-8")
                self._send_response(
                    HTTPStatus.OK, "application/json; charset=utf-8", body
                )
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_response(
            self, status: HTTPStatus, content_type: str, body: bytes
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), DashboardRequestHandler)


def _render_html() -> bytes:
    html = _read_asset("index.html").decode("utf-8")
    return html.replace("__POLL_INTERVAL_MS__", str(DASHBOARD_POLL_INTERVAL_MS)).encode(
        "utf-8"
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the LED matrix dashboard.")
    parser.add_argument("--host", default=DASHBOARD_HOST, help="Dashboard bind host.")
    parser.add_argument(
        "--port", type=int, default=DASHBOARD_PORT, help="Dashboard bind port."
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        help="SQLite database path to read runtime state from.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    server = create_dashboard_server(
        host=args.host, port=args.port, db_path=args.db_path
    )
    print(f"Dashboard available at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
