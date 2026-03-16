import argparse
import json
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from admin_auth import authenticate_admin, get_admin_status, logout_admin
from config import (
    ADMIN_SESSION_TTL_SECONDS,
    ADMIN_SESSION_COOKIE_NAME,
    ADMIN_SESSION_COOKIE_SECURE,
    DASHBOARD_HOST,
    DASHBOARD_POLL_INTERVAL_MS,
    DASHBOARD_PORT,
    DB_PATH,
)
from current_display_state import load_current_display_state
from runtime_control import (
    get_runtime_control_state,
    request_skip_category,
    request_switch_category,
    set_control_lock,
)

ASSETS_DIR = Path(__file__).with_name("dashboard_assets")
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
    "/dashboard.js": ("dashboard.js", "application/javascript; charset=utf-8"),
}
API_PATH = "/api/current-display-state"
CONTROL_STATE_API_PATH = "/api/control-state"
SKIP_CATEGORY_API_PATH = "/api/skip-category"
SWITCH_CATEGORY_API_PATH = "/api/switch-category"
ADMIN_LOGIN_API_PATH = "/api/admin/login"
ADMIN_LOGOUT_API_PATH = "/api/admin/logout"
ADMIN_CONTROL_LOCK_API_PATH = "/api/admin/control-lock"

CSP_HEADER = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' https: data:;"
)


def _read_asset(filename: str) -> bytes:
    return (ASSETS_DIR / filename).read_bytes()


def _cookie_header(session_token: str) -> str:
    cookie = SimpleCookie()
    cookie[ADMIN_SESSION_COOKIE_NAME] = session_token
    cookie[ADMIN_SESSION_COOKIE_NAME]["httponly"] = True
    cookie[ADMIN_SESSION_COOKIE_NAME]["max-age"] = ADMIN_SESSION_TTL_SECONDS
    cookie[ADMIN_SESSION_COOKIE_NAME]["path"] = "/"
    cookie[ADMIN_SESSION_COOKIE_NAME]["samesite"] = "Strict"
    if ADMIN_SESSION_COOKIE_SECURE:
        cookie[ADMIN_SESSION_COOKIE_NAME]["secure"] = True
    return cookie.output(header="").strip()


def _expired_cookie_header() -> str:
    cookie = SimpleCookie()
    cookie[ADMIN_SESSION_COOKIE_NAME] = ""
    cookie[ADMIN_SESSION_COOKIE_NAME]["expires"] = "Thu, 01 Jan 1970 00:00:00 GMT"
    cookie[ADMIN_SESSION_COOKIE_NAME]["max-age"] = 0
    cookie[ADMIN_SESSION_COOKIE_NAME]["httponly"] = True
    cookie[ADMIN_SESSION_COOKIE_NAME]["path"] = "/"
    cookie[ADMIN_SESSION_COOKIE_NAME]["samesite"] = "Strict"
    if ADMIN_SESSION_COOKIE_SECURE:
        cookie[ADMIN_SESSION_COOKIE_NAME]["secure"] = True
    return cookie.output(header="").strip()


def create_dashboard_server(
    host: str = DASHBOARD_HOST,
    port: int = DASHBOARD_PORT,
    db_path: str = DB_PATH,
) -> ThreadingHTTPServer:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = self.path.split("?", 1)[0]

            if route == API_PATH:
                self._send_json(HTTPStatus.OK, load_current_display_state(db_path))
                return

            if route == CONTROL_STATE_API_PATH:
                self._send_json(HTTPStatus.OK, self._build_control_state_payload())
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
                admin_status = self._get_admin_status()
                result = request_skip_category(
                    db_path=db_path,
                    is_admin=admin_status["authenticated"],
                )
                self._send_json(self._control_status_code(result), result)
                return

            if route == SWITCH_CATEGORY_API_PATH:
                admin_status = self._get_admin_status()
                try:
                    payload = self._read_json_body()
                    category = self._require_text_field(payload, "category")
                    result = request_switch_category(
                        category=category,
                        db_path=db_path,
                        is_admin=admin_status["authenticated"],
                    )
                except ValueError as error:
                    self._send_json_error(HTTPStatus.BAD_REQUEST, str(error))
                    return

                self._send_json(self._control_status_code(result), result)
                return

            if route == ADMIN_LOGIN_API_PATH:
                try:
                    payload = self._read_json_body()
                    username = self._require_text_field(payload, "username")
                    password = self._require_text_field(payload, "password")
                except ValueError as error:
                    self._send_json_error(HTTPStatus.BAD_REQUEST, str(error))
                    return

                result = authenticate_admin(
                    username=username,
                    password=password,
                    client_ip=self.client_address[0],
                    db_path=db_path,
                )
                headers = {}
                if result.get("authenticated") and result.get("session_token"):
                    headers["Set-Cookie"] = _cookie_header(result["session_token"])

                response_body = {
                    k: v for k, v in result.items() if k != "session_token"
                }
                status = HTTPStatus.OK
                if result["status"] == "invalid_credentials":
                    status = HTTPStatus.UNAUTHORIZED
                elif result["status"] == "locked":
                    status = HTTPStatus.TOO_MANY_REQUESTS
                    if result.get("retry_after_seconds"):
                        headers["Retry-After"] = str(result["retry_after_seconds"])
                elif result["status"] == "disabled":
                    status = HTTPStatus.SERVICE_UNAVAILABLE

                self._send_json(status, response_body, extra_headers=headers)
                return

            if route == ADMIN_LOGOUT_API_PATH:
                logout_admin(self._get_session_token(), db_path=db_path)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "authenticated": False,
                        "status": "logged_out",
                    },
                    extra_headers={"Set-Cookie": _expired_cookie_header()},
                )
                return

            if route == ADMIN_CONTROL_LOCK_API_PATH:
                if not self._require_admin():
                    return

                try:
                    payload = self._read_json_body()
                    action = self._require_text_field(payload, "action")
                    locked = self._require_bool_field(payload, "locked")
                    control_state = set_control_lock(action, locked, db_path=db_path)
                except ValueError as error:
                    self._send_json_error(HTTPStatus.BAD_REQUEST, str(error))
                    return

                self._send_json(
                    HTTPStatus.OK,
                    {
                        "updated": True,
                        "control": control_state,
                    },
                )
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send_json(
            self,
            status: HTTPStatus,
            payload: dict,
            *,
            extra_headers: dict | None = None,
        ) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._send_response(
                status,
                "application/json; charset=utf-8",
                body,
                extra_headers=extra_headers,
            )

        def _send_json_error(
            self,
            status: HTTPStatus,
            message: str,
            *,
            extra: dict | None = None,
            headers: dict | None = None,
        ) -> None:
            payload = {"error": message}
            if extra:
                payload.update(extra)
            self._send_json(status, payload, extra_headers=headers)

        def _send_response(
            self,
            status: HTTPStatus,
            content_type: str,
            body: bytes,
            *,
            extra_headers: dict | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP_HEADER)
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if extra_headers:
                for header, value in extra_headers.items():
                    self.send_header(header, value)
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError("Request body must be valid JSON.") from error

            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")

            return payload

        def _require_text_field(self, payload: dict, field_name: str) -> str:
            value = payload.get(field_name)
            if value is None or not str(value).strip():
                raise ValueError(f"'{field_name}' is required.")
            return str(value).strip()

        def _require_bool_field(self, payload: dict, field_name: str) -> bool:
            value = payload.get(field_name)
            if not isinstance(value, bool):
                raise ValueError(f"'{field_name}' must be a boolean.")
            return value

        def _get_session_token(self) -> str | None:
            raw_cookie = self.headers.get("Cookie", "")
            if not raw_cookie:
                return None

            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            morsel = cookie.get(ADMIN_SESSION_COOKIE_NAME)
            if morsel is None:
                return None
            return morsel.value

        def _get_admin_status(self) -> dict:
            return get_admin_status(
                self._get_session_token(),
                db_path=db_path,
            )

        def _require_admin(self) -> bool:
            admin_status = self._get_admin_status()
            if admin_status["authenticated"]:
                return True

            self._send_json_error(
                HTTPStatus.UNAUTHORIZED,
                "Admin authentication is required for this action.",
                extra={"authenticated": False},
                headers={"Set-Cookie": _expired_cookie_header()},
            )
            return False

        def _build_control_state_payload(self) -> dict:
            admin_status = self._get_admin_status()
            return {
                "auth": admin_status,
                "controls": get_runtime_control_state(
                    db_path=db_path,
                    is_admin=admin_status["authenticated"],
                ),
            }

        def _control_status_code(self, result: dict) -> HTTPStatus:
            if result.get("accepted"):
                return HTTPStatus.OK
            if result.get("locked"):
                return HTTPStatus.LOCKED
            if result.get("rate_limited"):
                return HTTPStatus.TOO_MANY_REQUESTS
            return HTTPStatus.CONFLICT

    return ThreadingHTTPServer((host, port), DashboardRequestHandler)


def _render_html() -> bytes:
    html = _read_asset("index.html").decode("utf-8")
    replacements = {
        "__POLL_INTERVAL_MS__": str(DASHBOARD_POLL_INTERVAL_MS),
        "__CURRENT_DISPLAY_API__": API_PATH,
        "__CONTROL_STATE_API__": CONTROL_STATE_API_PATH,
        "__SKIP_API__": SKIP_CATEGORY_API_PATH,
        "__SWITCH_API__": SWITCH_CATEGORY_API_PATH,
        "__ADMIN_LOGIN_API__": ADMIN_LOGIN_API_PATH,
        "__ADMIN_LOGOUT_API__": ADMIN_LOGOUT_API_PATH,
        "__ADMIN_CONTROL_LOCK_API__": ADMIN_CONTROL_LOCK_API_PATH,
    }
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return html.encode("utf-8")


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
