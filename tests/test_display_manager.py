from datetime import datetime as real_datetime
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

    left_only = _non_default_mask(display._compose_pokemon_frame(name_panel=name_panel))
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
                "text_brightness": 100,
                "background_brightness": 100,
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


def test_render_custom_text_brightness_controls_text_and_background_independently() -> (
    None
):
    display = display_manager.DisplayManager(use_matrix=False)
    base_style = {
        "font_family": "sans",
        "font_size": 24,
        "underline": True,
        "text_color": "orange",
        "background_color": "blue",
        "alignment": "center",
    }
    bright_payload = {
        "category": "custom_text",
        "data": {
            "text": "M",
            "style": {
                **base_style,
                "text_brightness": 100,
                "background_brightness": 100,
            },
        },
    }
    text_dim_payload = {
        "category": "custom_text",
        "data": {
            "text": "M",
            "style": {
                **base_style,
                "text_brightness": 40,
                "background_brightness": 100,
            },
        },
    }
    background_dim_payload = {
        "category": "custom_text",
        "data": {
            "text": "M",
            "style": {
                **base_style,
                "text_brightness": 100,
                "background_brightness": 40,
            },
        },
    }
    full_background_only_payload = {
        "category": "custom_text",
        "data": {
            "text": "",
            "style": {
                **base_style,
                "text_brightness": 100,
                "background_brightness": 100,
            },
        },
    }
    dim_background_only_payload = {
        "category": "custom_text",
        "data": {
            "text": "",
            "style": {
                **base_style,
                "text_brightness": 100,
                "background_brightness": 40,
            },
        },
    }

    bright_frame = display.render_payload(bright_payload)
    text_dim_frame = display.render_payload(text_dim_payload)
    background_dim_frame = display.render_payload(background_dim_payload)
    full_background_only_frame = display.render_payload(full_background_only_payload)
    dim_background_only_frame = display.render_payload(dim_background_only_payload)
    bright_pixels = np.array(bright_frame)
    text_dim_pixels = np.array(text_dim_frame)
    background_dim_pixels = np.array(background_dim_frame)
    full_background_only_pixels = np.array(full_background_only_frame)
    dim_background_only_pixels = np.array(dim_background_only_frame)
    text_mask = np.any(bright_pixels != full_background_only_pixels, axis=-1)

    assert text_mask.any()
    assert (
        tuple(bright_frame.getpixel((0, 0)))
        == display_manager.CUSTOM_TEXT_COLORS["blue"]
    )
    assert (
        tuple(text_dim_frame.getpixel((0, 0)))
        == display_manager.CUSTOM_TEXT_COLORS["blue"]
    )
    assert tuple(background_dim_frame.getpixel((0, 0))) == (4, 53, 102, 255)
    assert np.array_equal(text_dim_pixels[~text_mask], bright_pixels[~text_mask])
    assert int(text_dim_pixels[text_mask, :3].sum()) < int(
        bright_pixels[text_mask, :3].sum()
    )
    assert np.array_equal(
        background_dim_pixels[~text_mask],
        dim_background_only_pixels[~text_mask],
    )
    assert int(background_dim_pixels[~text_mask, :3].sum()) < int(
        bright_pixels[~text_mask, :3].sum()
    )
    assert np.array_equal(text_dim_pixels[..., 3], bright_pixels[..., 3])
    assert np.array_equal(background_dim_pixels[..., 3], bright_pixels[..., 3])


def test_weather_header_uses_live_clock_instead_of_payload_timestamp(
    monkeypatch,
) -> None:
    class FakeDateTime:
        @classmethod
        def now(cls):
            return real_datetime(2026, 3, 23, 14, 5, 6)

    display = display_manager.DisplayManager(use_matrix=False)
    payload = {
        "time": "1999-12-31 23:59:59",
        "data": {
            "location": "Erie, PA",
            "condition": "Cloudy",
            "temperature_f": 37,
            "wind_mph": 11,
        },
    }

    monkeypatch.setattr(display_manager, "datetime", FakeDateTime)

    assert display._weather_date_text(payload) == "Mar 23, 2026"
    assert display._weather_time_text() == "2:05:06 PM"


def test_weather_ticker_uses_deadline_based_frame_timing(monkeypatch) -> None:
    class FakeClock:
        def __init__(self) -> None:
            self.now = 0.0

        def time(self) -> float:
            return self.now

        def perf_counter(self) -> float:
            return self.now

        def sleep(self, duration: float) -> None:
            self.now += max(0.0, duration)

    class ProbeDisplay(display_manager.DisplayManager):
        def __init__(self) -> None:
            super().__init__(use_matrix=False)
            self.frame_times: list[float] = []

        def _transition_to(
            self,
            target_image,
            preview_name=None,
            steps=6,
            delay=0.035,
            should_interrupt=None,
        ) -> bool:
            self.frame_times.append(clock.perf_counter())
            self.last_frame = self._prepare_image(target_image)
            return False

        def _show_frame(self, image, preview_name=None) -> None:
            self.frame_times.append(clock.perf_counter())
            self.last_frame = self._prepare_image(image)

        def _weather_ticker_frame(
            self,
            payload: dict,
            ticker: str,
            offset_px: int,
            *,
            frame_time=None,
            base_frame=None,
            ticker_segments=None,
        ):
            clock.now += 0.03
            return super()._weather_ticker_frame(
                payload,
                ticker,
                offset_px,
                frame_time=frame_time,
                base_frame=base_frame,
                ticker_segments=ticker_segments,
            )

    clock = FakeClock()
    monkeypatch.setattr(display_manager.time, "time", clock.time)
    monkeypatch.setattr(display_manager.time, "perf_counter", clock.perf_counter)
    monkeypatch.setattr(display_manager.time, "sleep", clock.sleep)

    payload = {
        "slot_key": "2026-03-23:168",
        "data": {
            "location": "Erie, PA",
            "condition": "Cloudy",
            "temperature_f": 37,
            "wind_mph": 11,
        },
    }

    display = ProbeDisplay()
    display._animate_weather_ticker(
        payload,
        duration_seconds=1,
        safe_slot="2026-03-23-168",
    )

    intervals = [
        round(current - previous, 2)
        for previous, current in zip(display.frame_times, display.frame_times[1:])
    ]

    assert len(intervals) >= 2
    assert intervals[1:] == [display_manager.WEATHER_TICKER_FRAME_DELAY] * (
        len(intervals) - 1
    )
