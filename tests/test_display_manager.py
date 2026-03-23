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


POKEMON_SAMPLE = {
    "name": "Bulbasaur",
    "types": ["Grass", "Poison"],
    "hp": 45,
    "attack": 49,
    "defense": 49,
    "image_url": "https://example.test/bulbasaur.png",
}


def _non_default_mask(image) -> np.ndarray:
    pixels = np.array(image)
    background = np.array(display_manager.DEFAULT_BG, dtype=np.uint8)
    return np.any(pixels != background, axis=-1)


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


def test_render_pokemon_base_uses_all_three_panels(monkeypatch) -> None:
    display = display_manager.DisplayManager(use_matrix=False)
    art = display_manager.Image.new("RGBA", (48, 48), (255, 64, 32, 255))
    monkeypatch.setattr(display, "_pokemon_artwork", lambda data: art)

    frame = display._render_pokemon_base(POKEMON_SAMPLE)
    mask = _non_default_mask(frame)
    panel_width = display.panel_width

    assert mask[:, :panel_width].any()
    assert mask[:, panel_width : panel_width * 2].any()
    assert mask[:, panel_width * 2 :].any()


def test_compose_pokemon_frame_keeps_each_panel_in_its_region(monkeypatch) -> None:
    display = display_manager.DisplayManager(use_matrix=False)
    art = display_manager.Image.new("RGBA", (48, 48), (255, 64, 32, 255))
    monkeypatch.setattr(display, "_pokemon_artwork", lambda data: art)

    name_panel = display._render_pokemon_center_title(POKEMON_SAMPLE)
    stat_panel = display._pokemon_stat_frames(POKEMON_SAMPLE)[0]
    image_panel = display._render_pokemon_image_frame(POKEMON_SAMPLE)
    panel_width = display.panel_width

    left_only = _non_default_mask(
        display._compose_pokemon_frame(name_panel=name_panel)
    )
    assert left_only[:, :panel_width].any()
    assert not left_only[:, panel_width:].any()

    middle_only = _non_default_mask(
        display._compose_pokemon_frame(stat_panel=stat_panel)
    )
    assert middle_only[:, panel_width : panel_width * 2].any()
    assert not middle_only[:, :panel_width].any()
    assert not middle_only[:, panel_width * 2 :].any()

    right_only = _non_default_mask(
        display._compose_pokemon_frame(image_panel=image_panel)
    )
    assert right_only[:, panel_width * 2 :].any()
    assert not right_only[:, : panel_width * 2].any()


def test_render_custom_text_payload_uses_requested_palette_and_content() -> None:
    display = display_manager.DisplayManager(use_matrix=False)
    payload = {
        "category": "custom_text",
        "data": {
            "text": "Matrix maintenance at 3 PM",
            "style": {
                "bold": True,
                "italic": False,
                "underline": True,
                "font_family": "mono",
                "font_size": 18,
                "text_color": "orange",
                "background_color": "blue",
                "alignment": "center",
            },
        },
    }

    frame = display.render_payload(payload)
    pixels = np.array(frame)
    background = np.array(display_manager.CUSTOM_TEXT_COLORS["blue"], dtype=np.uint8)

    assert tuple(frame.getpixel((0, 0))) == display_manager.CUSTOM_TEXT_COLORS["blue"]
    assert np.any(np.any(pixels != background, axis=-1))
