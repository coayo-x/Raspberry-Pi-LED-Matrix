import subprocess
import threading
from typing import Callable

from config import (
    BACKEND_SERVICE_NAME,
    FRONTEND_SERVICE_NAME,
    SERVICE_CONTROL_TIMEOUT_SECONDS,
    SYSTEMCTL_BIN,
    SYSTEMCTL_USE_SUDO,
)

SERVICE_TARGETS = {
    "backend": BACKEND_SERVICE_NAME,
    "frontend": FRONTEND_SERVICE_NAME,
}
SERVICE_ACTIONS = {"stop", "restart"}


def get_service_control_config() -> dict:
    return {
        "systemctl_bin": SYSTEMCTL_BIN,
        "use_sudo": SYSTEMCTL_USE_SUDO,
        "backend_service": BACKEND_SERVICE_NAME,
        "frontend_service": FRONTEND_SERVICE_NAME,
        "available_targets": sorted(SERVICE_TARGETS),
        "available_actions": sorted(SERVICE_ACTIONS),
    }


def _normalize_service(service: str) -> str:
    normalized = str(service).strip().lower()
    if normalized not in SERVICE_TARGETS:
        raise ValueError(
            f"Invalid service '{service}'. Expected one of: {', '.join(sorted(SERVICE_TARGETS))}"
        )
    return normalized


def _normalize_action(action: str) -> str:
    normalized = str(action).strip().lower()
    if normalized not in SERVICE_ACTIONS:
        raise ValueError(
            f"Invalid action '{action}'. Expected one of: {', '.join(sorted(SERVICE_ACTIONS))}"
        )
    return normalized


def build_service_command(service: str, action: str) -> list[str]:
    normalized_service = _normalize_service(service)
    normalized_action = _normalize_action(action)
    command = [SYSTEMCTL_BIN, normalized_action, SERVICE_TARGETS[normalized_service]]
    if SYSTEMCTL_USE_SUDO:
        return ["sudo", "-n", *command]
    return command


def execute_service_action(
    service: str,
    action: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict:
    command = build_service_command(service, action)
    active_runner = runner or subprocess.run
    result = active_runner(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=SERVICE_CONTROL_TIMEOUT_SECONDS,
    )
    return {
        "ok": result.returncode == 0,
        "service": _normalize_service(service),
        "action": _normalize_action(action),
        "service_name": SERVICE_TARGETS[_normalize_service(service)],
        "command": command,
        "returncode": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }


def schedule_service_action(
    service: str,
    action: str,
    *,
    delay_seconds: float = 0.25,
    executor: Callable[[str, str], object] | None = None,
) -> dict:
    normalized_service = _normalize_service(service)
    normalized_action = _normalize_action(action)
    active_executor = executor or (lambda svc, act: execute_service_action(svc, act))

    timer = threading.Timer(
        delay_seconds,
        active_executor,
        args=(normalized_service, normalized_action),
    )
    timer.daemon = True
    timer.start()
    return {
        "scheduled": True,
        "service": normalized_service,
        "action": normalized_action,
        "delay_seconds": delay_seconds,
        "service_name": SERVICE_TARGETS[normalized_service],
    }
