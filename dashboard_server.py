import argparse
import json
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from admin_auth import authenticate_admin, get_admin_status, logout_admin
from config import (
    ADMIN_SESSION_COOKIE_NAME,
    ADMIN_SESSION_COOKIE_SECURE,
    ADMIN_SESSION_TTL_SECONDS,
    DASHBOARD_HOST,
    DASHBOARD_POLL_INTERVAL_MS,
    DASHBOARD_PORT,
    DB_PATH,
)
from current_display_state import load_current_display_state
from runtime_control import (
    get_controls_lock_state,
    get_runtime_control_state,
    request_skip_category,
    request_switch_category,
    set_controls_lock,
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
LOGIN_PAGE_PATH = "/login"
API_PATH = "/api/current-display-state"
CONTROL_STATE_API_PATH = "/api/control-state"
SKIP_CATEGORY_API_PATH = "/api/skip-category"
SWITCH_CATEGORY_API_PATH = "/api/switch-category"
ADMIN_LOGIN_API_PATH = "/api/admin/login"
ADMIN_LOGOUT_API_PATH = "/api/admin/logout"
ADMIN_CONTROL_LOCK_API_PATH = "/api/admin/control-lock"
LOCK_CONTROLS_API_PATH = "/api/lock-controls"
UNLOCK_CONTROLS_API_PATH = "/api/unlock-controls"

CSP_HEADER = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' https: data:;"
)
LOGIN_CSP_HEADER = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "img-src 'self' data:;"
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


def _render_login_html(configured: bool) -> bytes:
    html = """
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>LED Matrix Dashboard Login</title>
    <style>
        :root {
            color-scheme: dark;
            --bg-1: #08111b;
            --bg-2: #102134;
            --panel: rgba(10, 18, 28, 0.92);
            --border: rgba(164, 192, 214, 0.18);
            --text-main: #eef5fb;
            --text-muted: #9db1c5;
            --accent: #6ed4bf;
            --danger: #ffb09a;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            padding: 20px;
            font-family: "Gill Sans", "Trebuchet MS", sans-serif;
            color: var(--text-main);
            background:
                radial-gradient(circle at top left, rgba(110, 212, 191, 0.14), transparent 28%),
                linear-gradient(155deg, var(--bg-1) 0%, var(--bg-2) 100%);
        }

        .login-card {
            width: min(100%, 420px);
            padding: 24px;
            border-radius: 20px;
            border: 1px solid var(--border);
            background: var(--panel);
            box-shadow: 0 18px 36px rgba(1, 8, 18, 0.45);
        }

        .eyebrow {
            margin: 0;
            color: var(--accent);
            letter-spacing: 0.16em;
            text-transform: uppercase;
            font-size: 0.68rem;
        }

        h1 {
            margin: 8px 0 10px;
            font-family: Georgia, "Palatino Linotype", serif;
            font-size: 1.9rem;
            line-height: 1.05;
        }

        p {
            margin: 0;
            color: var(--text-muted);
            line-height: 1.45;
        }

        form {
            display: grid;
            gap: 12px;
            margin-top: 18px;
        }

        label {
            display: grid;
            gap: 6px;
            font-size: 0.92rem;
            color: var(--text-main);
        }

        input,
        button {
            font: inherit;
            border-radius: 12px;
        }

        input {
            width: 100%;
            padding: 10px 12px;
            border: 1px solid rgba(140, 230, 255, 0.2);
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-main);
        }

        button {
            border: 1px solid rgba(140, 230, 255, 0.24);
            background: linear-gradient(180deg, rgba(140, 230, 255, 0.18), rgba(110, 212, 191, 0.12));
            color: var(--text-main);
            cursor: pointer;
            font-weight: 700;
            letter-spacing: 0.04em;
            padding: 10px 14px;
        }

        button:disabled {
            cursor: not-allowed;
            opacity: 0.6;
        }

        .status {
            margin-top: 14px;
            min-height: 1.4em;
        }

        .status[data-state="error"] {
            color: var(--danger);
        }

        .status[data-state="success"] {
            color: var(--accent);
        }
    </style>
</head>
<body>
    <main class="login-card">
        <p class="eyebrow">Restricted Access</p>
        <h1>LED Matrix Dashboard</h1>
        <p id="login-copy">
            Sign in with the configured dashboard credentials to manage admin control locks.
        </p>

        <form id="login-form" __FORM_ATTRS__>
            <label>
                <span>Username</span>
                <input id="username" name="username" type="text" autocomplete="username" __INPUT_ATTRS__>
            </label>
            <label>
                <span>Password</span>
                <input id="password" name="password" type="password" autocomplete="current-password" __INPUT_ATTRS__>
            </label>
            <button id="login-button" type="submit" __BUTTON_ATTRS__>Sign In</button>
        </form>

        <p class="status" id="status" data-state="idle">__INITIAL_STATUS__</p>
    </main>

    <script>
        const loginApi = "__LOGIN_API__";
        const configured = __CONFIGURED__;
        const redirectPath = "/";
        const form = document.getElementById("login-form");
        const button = document.getElementById("login-button");
        const status = document.getElementById("status");
        const copy = document.getElementById("login-copy");

        if (!configured) {
            copy.textContent =
                "Dashboard access is disabled until ADMIN_USERNAME and ADMIN_PASSWORD_HASH are configured on this host.";
        }

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!configured) {
                return;
            }

            const username = document.getElementById("username").value.trim();
            const password = document.getElementById("password").value;
            if (!username || !password) {
                status.dataset.state = "error";
                status.textContent = "Username and password are required.";
                return;
            }

            button.disabled = true;
            status.dataset.state = "idle";
            status.textContent = "Signing in...";

            try {
                const response = await fetch(loginApi, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password }),
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    status.dataset.state = "error";
                    status.textContent = payload.error || `HTTP ${response.status}`;
                    return;
                }

                status.dataset.state = "success";
                status.textContent = "Authentication successful. Redirecting...";
                window.location.assign(redirectPath);
            } catch (error) {
                status.dataset.state = "error";
                status.textContent = error?.message || "Sign-in failed.";
            } finally {
                button.disabled = false;
                document.getElementById("password").value = "";
            }
        });
    </script>
</body>
</html>
"""
    return (
        html.replace("__LOGIN_API__", ADMIN_LOGIN_API_PATH)
        .replace("__CONFIGURED__", "true" if configured else "false")
        .replace(
            "__FORM_ATTRS__",
            "" if configured else 'aria-disabled="true"',
        )
        .replace("__INPUT_ATTRS__", "" if configured else "disabled")
        .replace("__BUTTON_ATTRS__", "" if configured else "disabled")
        .replace(
            "__INITIAL_STATUS__",
            "Dashboard authentication is ready."
            if configured
            else "Dashboard credentials are not configured on this host.",
        )
        .encode("utf-8")
    )


def create_dashboard_server(
    host: str = DASHBOARD_HOST,
    port: int = DASHBOARD_PORT,
    db_path: str = DB_PATH,
) -> ThreadingHTTPServer:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            route = self.path.split("?", 1)[0]

            if route == LOGIN_PAGE_PATH:
                admin_status = self._get_admin_status()
                if admin_status["authenticated"]:
                    self._send_redirect("/")
                else:
                    self._send_login_page(admin_status["configured"])
                return

            if route == API_PATH:
                self._send_json(HTTPStatus.OK, load_current_display_state(db_path))
                return

            if route == CONTROL_STATE_API_PATH:
                admin_status = self._get_admin_status()
                self._send_json(
                    HTTPStatus.OK,
                    self._build_control_state_payload(admin_status),
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
                    key: value
                    for key, value in result.items()
                    if key != "session_token"
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

            if route == ADMIN_LOGOUT_API_PATH:
                if self._require_authenticated_api() is None:
                    return

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

            if route == LOCK_CONTROLS_API_PATH:
                if self._require_authenticated_api() is None:
                    return

                controls_locked = set_controls_lock(True, db_path=db_path)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "updated": True,
                        "controls_locked": controls_locked,
                        "controls": get_runtime_control_state(
                            db_path=db_path,
                            is_admin=True,
                        ),
                    },
                )
                return

            if route == UNLOCK_CONTROLS_API_PATH:
                if self._require_authenticated_api() is None:
                    return

                controls_locked = set_controls_lock(False, db_path=db_path)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "updated": True,
                        "controls_locked": controls_locked,
                        "controls": get_runtime_control_state(
                            db_path=db_path,
                            is_admin=True,
                        ),
                    },
                )
                return

            if route == ADMIN_CONTROL_LOCK_API_PATH:
                if self._require_authenticated_api() is None:
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
            content_security_policy: str = CSP_HEADER,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", content_security_policy)
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if extra_headers:
                for header, value in extra_headers.items():
                    self.send_header(header, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_redirect(
            self, location: str, *, extra_headers: dict | None = None
        ) -> None:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if extra_headers:
                for header, value in extra_headers.items():
                    self.send_header(header, value)
            self.end_headers()

        def _send_login_page(self, configured: bool) -> None:
            self._send_response(
                HTTPStatus.OK,
                "text/html; charset=utf-8",
                _render_login_html(configured),
                content_security_policy=LOGIN_CSP_HEADER,
            )

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

        def _require_authenticated_api(self) -> dict | None:
            admin_status = self._get_admin_status()
            if admin_status["authenticated"]:
                return admin_status

            message = "Dashboard authentication is required."
            if not admin_status["configured"]:
                message = (
                    "Dashboard authentication is not configured on this host."
                )

            self._send_json_error(
                HTTPStatus.UNAUTHORIZED,
                message,
                extra={
                    "authenticated": False,
                    "configured": admin_status["configured"],
                },
                headers={"Set-Cookie": _expired_cookie_header()},
            )
            return None

        def _build_control_state_payload(self, admin_status: dict | None = None) -> dict:
            auth_state = admin_status or self._get_admin_status()
            return {
                "auth": auth_state,
                "controls_locked": get_controls_lock_state(db_path),
                "controls": get_runtime_control_state(
                    db_path=db_path,
                    is_admin=auth_state["authenticated"],
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
        "__LOCK_CONTROLS_API__": LOCK_CONTROLS_API_PATH,
        "__UNLOCK_CONTROLS_API__": UNLOCK_CONTROLS_API_PATH,
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
