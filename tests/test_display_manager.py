from types import SimpleNamespace

import pytest

import display_manager


class FakeGeometry:
    def __init__(self, **kwargs) -> None:
        self.width = kwargs["width"]
        self.height = kwargs["height"]
        self.n_addr_lines = kwargs["n_addr_lines"]
        self.rotation = kwargs.get("rotation")


class FakeMatrix:
    def __init__(self, colorspace, pinout, framebuffer, geometry) -> None:
        self.colorspace = colorspace
        self.pinout = pinout
        self.framebuffer = framebuffer
        self.geometry = geometry
        self.show_calls = 0

    def show(self) -> None:
        self.show_calls += 1


def test_matrix_initialization_uses_multi_panel_geometry(monkeypatch) -> None:
    fake_piomatter = SimpleNamespace(
        Orientation=SimpleNamespace(Normal="normal"),
        Pinout=SimpleNamespace(AdafruitMatrixHatBGR="hat-bgr"),
        Colorspace=SimpleNamespace(RGB888Packed="rgb888packed"),
        Geometry=FakeGeometry,
        PioMatter=FakeMatrix,
    )

    monkeypatch.setattr(display_manager, "piomatter", fake_piomatter)
    display = display_manager.DisplayManager(use_matrix=True)
    frame = display_manager.Image.new(
        "RGBA",
        (display_manager.WIDTH, display_manager.HEIGHT),
        (255, 64, 32, 255),
    )
    display._show_frame(frame)

    assert display.use_matrix is True
    assert display.framebuffer.shape == (
        display_manager.HEIGHT,
        display_manager.WIDTH,
        3,
    )
    assert display.matrix is not None
    assert display.matrix.geometry.width == display_manager.WIDTH
    assert display.matrix.geometry.height == display_manager.HEIGHT
    assert display.matrix.geometry.n_addr_lines == display_manager.MATRIX_ADDR_LINES
    assert display.matrix.geometry.rotation == "normal"
    assert display.matrix.pinout == "hat-bgr"
    assert display.matrix.colorspace == "rgb888packed"
    assert display.matrix.show_calls == 1
    assert display.framebuffer.sum() > 0
    assert display.last_frame is not None


def test_matrix_initialization_requires_piomatter_backend(monkeypatch) -> None:
    monkeypatch.setattr(display_manager, "piomatter", None)

    with pytest.raises(
        RuntimeError,
        match="Matrix output requested but adafruit_blinka_raspberry_pi5_piomatter is not installed.",
    ):
        display_manager.DisplayManager(use_matrix=True)
