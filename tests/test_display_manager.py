from types import SimpleNamespace

import numpy as np
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


def _non_background_mask(image, background) -> np.ndarray:
    pixels = np.array(image)
    background_pixel = np.array(background, dtype=np.uint8)
    return np.any(pixels != background_pixel, axis=-1)


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


def test_render_custom_text_payload_uses_requested_background_and_text() -> None:
    display = display_manager.DisplayManager(use_matrix=False)
    payload = {
        "slot_key": "2026-03-23:144",
        "time": "2026-03-23 12:00:00",
        "category": "custom_text",
        "data": {
            "text": "Hello matrix",
            "style": {
                "bold": True,
                "italic": False,
                "underline": True,
                "font_family": "sans",
                "font_size": 16,
                "text_color": "#abcdef",
                "background_color": "#102030",
                "alignment": "center",
            },
        },
    }

    image = display.render_payload(payload)
    pixels = np.array(image)

    assert tuple(pixels[0, 0]) == (16, 32, 48, 255)
    assert _non_background_mask(image, (16, 32, 48, 255)).any()


def test_render_custom_text_paginates_long_content() -> None:
    display = display_manager.DisplayManager(use_matrix=False)
    payload = {
        "slot_key": "2026-03-23:145",
        "time": "2026-03-23 12:05:00",
        "category": "custom_text",
        "data": {
            "text": " ".join(["scheduled maintenance"] * 30),
            "style": {
                "bold": False,
                "italic": False,
                "underline": False,
                "font_family": "mono",
                "font_size": 18,
                "text_color": "#ffffff",
                "background_color": "#000000",
                "alignment": "justify",
            },
        },
    }

    pages = display.render_custom_text_pages(payload)

    assert len(pages) >= 2
