import subprocess
import threading

import service_control


def test_build_service_command_respects_sudo_setting(monkeypatch) -> None:
    monkeypatch.setattr(service_control, "SYSTEMCTL_BIN", "/bin/systemctl")
    monkeypatch.setattr(service_control, "SYSTEMCTL_USE_SUDO", True)
    monkeypatch.setitem(
        service_control.SERVICE_TARGETS, "backend", "led-matrix.service"
    )

    command = service_control.build_service_command("backend", "restart")

    assert command == [
        "sudo",
        "-n",
        "/bin/systemctl",
        "restart",
        "led-matrix.service",
    ]


def test_execute_service_action_returns_runner_result(monkeypatch) -> None:
    monkeypatch.setattr(service_control, "SYSTEMCTL_BIN", "systemctl")
    monkeypatch.setattr(service_control, "SYSTEMCTL_USE_SUDO", False)
    monkeypatch.setattr(service_control, "SERVICE_CONTROL_TIMEOUT_SECONDS", 7)
    monkeypatch.setitem(
        service_control.SERVICE_TARGETS, "backend", "led-matrix.service"
    )

    def fake_runner(command, capture_output, text, check, timeout):
        assert command == ["systemctl", "restart", "led-matrix.service"]
        assert capture_output is True
        assert text is True
        assert check is False
        assert timeout == 7
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    result = service_control.execute_service_action(
        "backend",
        "restart",
        runner=fake_runner,
    )

    assert result["ok"] is True
    assert result["stdout"] == "ok"
    assert result["stderr"] == ""


def test_schedule_service_action_invokes_executor(monkeypatch) -> None:
    event = threading.Event()
    observed = {}

    monkeypatch.setitem(
        service_control.SERVICE_TARGETS, "frontend", "led-matrix-dashboard.service"
    )

    def fake_executor(service, action):
        observed["service"] = service
        observed["action"] = action
        event.set()

    result = service_control.schedule_service_action(
        "frontend",
        "stop",
        delay_seconds=0.01,
        executor=fake_executor,
    )

    assert result["scheduled"] is True
    assert event.wait(timeout=1) is True
    assert observed == {"service": "frontend", "action": "stop"}
