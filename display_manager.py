import io
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from config import ROTATION_INTERVAL

try:
    import adafruit_blinka_raspberry_pi5_piomatter as piomatter
except ImportError:
    piomatter = None


PANEL_ROWS = 32
PANEL_COLS = 64
PANEL_CHAIN_LENGTH = 3
MATRIX_ADDR_LINES = 4

PANEL_WIDTH = PANEL_COLS
WIDTH = PANEL_COLS * PANEL_CHAIN_LENGTH
HEIGHT = PANEL_ROWS
DEFAULT_BG = (0, 0, 0, 255)

TEXT_PRIMARY = (238, 242, 247, 255)
TEXT_SECONDARY = (149, 172, 191, 255)
TEXT_ACCENT = (124, 214, 255, 255)
TEXT_HIGHLIGHT = (255, 209, 118, 255)
PANEL_FILL = (9, 17, 27, 255)
PANEL_FILL_ALT = (12, 22, 34, 255)
PANEL_DIVIDER = (28, 56, 80, 255)
WEATHER_TEMP_COLD = (146, 214, 255, 255)
WEATHER_TEMP_WARM = (255, 208, 126, 255)
WEATHER_TICKER = (224, 232, 240, 255)
WEATHER_CONDITION_SUNNY = (255, 219, 112, 255)
WEATHER_CONDITION_CLOUDY = (168, 176, 186, 255)
WEATHER_CONDITION_RAIN = (118, 186, 255, 255)
WEATHER_DIVIDER_GLOW = (124, 214, 255, 255)
JOKE_LABEL = TEXT_HIGHLIGHT
JOKE_DELIVERY = (135, 230, 202, 255)
POKEMON_NAME = (255, 224, 134, 255)
POKEMON_DETAIL = (201, 219, 236, 255)
POKEMON_STAT_LABEL = (120, 182, 219, 255)
POKEMON_ART_FRAME = (72, 121, 161, 255)
ICON_MAIN = (110, 178, 226, 255)
ICON_ALT = (255, 209, 118, 255)
CUSTOM_TEXT_COLORS = {
    "red": (255, 59, 48, 255),
    "green": (52, 199, 89, 255),
    "blue": (10, 132, 255, 255),
    "yellow": (255, 214, 10, 255),
    "magenta": (255, 45, 85, 255),
    "cyan": (100, 210, 255, 255),
    "white": (245, 247, 250, 255),
    "black": (0, 0, 0, 255),
    "orange": (255, 159, 10, 255),
    "purple": (191, 90, 242, 255),
}
SNAKE_BODY = (52, 199, 89, 255)
SNAKE_HEAD = (255, 214, 10, 255)
SNAKE_FOOD = (255, 59, 48, 255)
SNAKE_OBSTACLE = (112, 128, 144, 255)
SNAKE_BORDER = (124, 214, 255, 255)
SNAKE_TEXT = (245, 247, 250, 255)

PANEL_PADDING = 4
WEATHER_HEADER_HEIGHT = 18
WEATHER_TICKER_Y = 21
WEATHER_TICKER_FRAME_DELAY = 0.08

GLOBAL_ROTATE_180 = True


class DisplayManager:
    def __init__(
        self,
        width: int = WIDTH,
        height: int = HEIGHT,
        use_matrix: bool = True,
        preview_dir: str = "preview_frames",
        save_previews: bool = False,
    ) -> None:
        self.width = width
        self.height = height
        self.use_matrix_requested = use_matrix
        self.use_matrix = False
        self.save_previews = save_previews
        self.preview_dir = Path(preview_dir)
        if self.save_previews:
            self.preview_dir.mkdir(parents=True, exist_ok=True)

        self.font = self._load_font(size=9)
        self.small_font = self._load_font(size=8)
        self.medium_font = self._load_font(size=10, bold=True)
        self.large_font = self._load_font(size=12, bold=True)
        self.hero_font = self._load_font(size=14, bold=True)
        self.line_height = self._get_line_height(self.font)
        self.small_line_height = self._get_line_height(self.small_font)
        self.medium_line_height = self._get_line_height(self.medium_font)
        self.large_line_height = self._get_line_height(self.large_font)
        self.hero_line_height = self._get_line_height(self.hero_font)
        self.panel_width = max(1, self.width // PANEL_CHAIN_LENGTH)

        self.matrix = None
        self.framebuffer = None
        self.last_frame: Optional[Image.Image] = None

        if self.use_matrix_requested:
            self._initialize_matrix()

    def _initialize_matrix(self) -> None:
        if piomatter is None:
            raise RuntimeError(
                "Matrix output requested but adafruit_blinka_raspberry_pi5_piomatter is not installed."
            )

        geometry_kwargs = {
            "width": self.width,
            "height": self.height,
            "n_addr_lines": MATRIX_ADDR_LINES,
        }
        orientation = getattr(getattr(piomatter, "Orientation", None), "Normal", None)
        if orientation is not None:
            geometry_kwargs["rotation"] = orientation

        geometry = piomatter.Geometry(**geometry_kwargs)
        pinout = getattr(piomatter.Pinout, "AdafruitMatrixHatRGB", None)
        if pinout is None:
            pinout = getattr(piomatter.Pinout, "AdafruitMatrixHat", None)
        if pinout is None:
            pinout = piomatter.Pinout.AdafruitMatrixHatBGR
        colorspace_name = (
            "RGB888Packed"
            if hasattr(piomatter.Colorspace, "RGB888Packed")
            else "RGB888"
        )
        colorspace = getattr(piomatter.Colorspace, colorspace_name)
        channel_count = 3 if colorspace_name == "RGB888Packed" else 4
        self.framebuffer = np.zeros(
            (geometry.height, geometry.width, channel_count), dtype=np.uint8
        )
        self.matrix = piomatter.PioMatter(
            colorspace, pinout, self.framebuffer, geometry
        )

        if self.matrix is None:
            raise RuntimeError("Matrix initialization returned None.")

        self.use_matrix = True

    def _load_font(self, size: int, *, bold: bool = False, mono: bool = False):
        if mono:
            names = ["DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf"]
            paths = [
                (
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
                    if bold
                    else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
                )
            ]
        else:
            names = [
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
                "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
            ]
            paths = [
                (
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                    if bold
                    else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                ),
                (
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
                    if bold
                    else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
                ),
            ]

        for name in names + paths:
            try:
                return ImageFont.truetype(name, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _load_styled_font(
        self,
        size: int,
        *,
        family: str = "sans",
        bold: bool = False,
        italic: bool = False,
    ):
        family_key = str(family).strip().lower()
        font_candidates = {
            "sans": {
                (False, False): [
                    "DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ],
                (True, False): [
                    "DejaVuSans-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                ],
                (False, True): [
                    "DejaVuSans-Oblique.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
                ],
                (True, True): [
                    "DejaVuSans-BoldOblique.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
                ],
            },
            "serif": {
                (False, False): [
                    "DejaVuSerif.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                ],
                (True, False): [
                    "DejaVuSerif-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                ],
                (False, True): [
                    "DejaVuSerif-Italic.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
                ],
                (True, True): [
                    "DejaVuSerif-BoldItalic.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
                ],
            },
            "mono": {
                (False, False): [
                    "DejaVuSansMono.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                ],
                (True, False): [
                    "DejaVuSansMono-Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                ],
                (False, True): [
                    "DejaVuSansMono-Oblique.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Oblique.ttf",
                ],
                (True, True): [
                    "DejaVuSansMono-BoldOblique.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-BoldOblique.ttf",
                ],
            },
        }

        candidates = font_candidates.get(family_key, font_candidates["sans"]).get(
            (bold, italic),
            [],
        )
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue

        return self._load_font(size=size, bold=bold, mono=family_key == "mono")

    def _get_line_height(self, font) -> int:
        bbox = font.getbbox("Ag")
        return max(7, bbox[3] - bbox[1] + 1)

    def _text_width(self, text: str, font=None) -> int:
        active_font = font or self.font
        return active_font.getbbox(str(text))[2]

    def _truncate_to_width(self, text: str, max_width_px: int, font=None) -> str:
        active_font = font or self.font
        value = str(text)
        if self._text_width(value, active_font) <= max_width_px:
            return value

        ellipsis = "..."
        while value and self._text_width(value + ellipsis, active_font) > max_width_px:
            value = value[:-1]
        return (value + ellipsis) if value else ""

    def _split_prefix_to_width(self, text: str, max_width_px: int, font=None) -> int:
        active_font = font or self.font
        if not text or max_width_px <= 0:
            return 0

        low = 1
        high = len(text)
        best = 0
        while low <= high:
            mid = (low + high) // 2
            if self._text_width(text[:mid], active_font) <= max_width_px:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        return max(1, best)

    def _wrap_text(self, text: str, width_px: int, font=None) -> list[str]:
        active_font = font or self.font
        cleaned = " ".join(str(text).split())
        if not cleaned or width_px <= 0:
            return [""]

        wrapped: list[str] = []
        words = cleaned.split(" ")
        line = ""

        for word in words:
            if self._text_width(word, active_font) > width_px:
                if line:
                    wrapped.append(line)
                    line = ""

                remaining = word
                while remaining:
                    split_at = self._split_prefix_to_width(
                        remaining, width_px, active_font
                    )
                    piece = remaining[:split_at]
                    remaining = remaining[split_at:]
                    if remaining:
                        wrapped.append(piece)
                    else:
                        line = piece
                continue

            candidate = f"{line} {word}".strip()
            if line and self._text_width(candidate, active_font) > width_px:
                wrapped.append(line)
                line = word
            else:
                line = candidate

        if line:
            wrapped.append(line)

        return wrapped or [""]

    def _custom_text_color(
        self, value: str | None, fallback
    ) -> tuple[int, int, int, int]:
        normalized = str(value or "").strip().lower()
        return CUSTOM_TEXT_COLORS.get(normalized, fallback)

    def _scale_custom_text_fill(
        self,
        fill: tuple[int, int, int, int],
        brightness_percent: int | float | None,
    ) -> tuple[int, int, int, int]:
        try:
            clamped_brightness = max(10, min(100, int(brightness_percent or 100)))
        except (TypeError, ValueError):
            clamped_brightness = 100

        if clamped_brightness >= 100:
            return fill

        factor = clamped_brightness / 100
        red, green, blue, alpha = fill
        return (
            int(round(red * factor)),
            int(round(green * factor)),
            int(round(blue * factor)),
            alpha,
        )

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        img = image.convert("RGBA").resize((self.width, self.height), Image.NEAREST)
        if GLOBAL_ROTATE_180:
            img = img.rotate(180, expand=False)
        return img

    def _push_prepared(self, image: Image.Image) -> None:
        if self.use_matrix and self.matrix is not None and self.framebuffer is not None:
            channel_count = self.framebuffer.shape[2]
            rgb_arr = np.array(image.convert("RGB"), dtype=np.uint8)
            if channel_count == 3:
                arr = rgb_arr
            else:
                alpha = np.full((self.height, self.width, 1), 255, dtype=np.uint8)
                arr = np.concatenate((rgb_arr, alpha), axis=2)
            self.framebuffer[:] = np.flipud(np.fliplr(arr))
            self.matrix.show()

    def _save_prepared(self, image: Image.Image, preview_name: Optional[str]) -> None:
        if self.save_previews and preview_name:
            image.save(self.preview_dir / preview_name)

    def _show_frame(
        self, image: Image.Image, preview_name: Optional[str] = None
    ) -> None:
        prepared = self._prepare_image(image)
        self._push_prepared(prepared)
        self._save_prepared(prepared, preview_name)
        self.last_frame = prepared

    def show_image(
        self, image: Image.Image, preview_name: Optional[str] = None
    ) -> None:
        self._show_frame(image, preview_name=preview_name)

    def _is_interrupted(
        self, should_interrupt: Optional[Callable[[], bool]] = None
    ) -> bool:
        return bool(should_interrupt and should_interrupt())

    def _sleep_with_interrupt(
        self,
        duration: float,
        should_interrupt: Optional[Callable[[], bool]] = None,
        interval: float = 0.05,
    ) -> bool:
        if duration <= 0:
            return self._is_interrupted(should_interrupt)

        end_time = time.time() + duration
        while time.time() < end_time:
            if self._is_interrupted(should_interrupt):
                return True

            time.sleep(min(interval, max(0.0, end_time - time.time())))

        return self._is_interrupted(should_interrupt)

    def _sleep_until(
        self,
        target_time: float,
        should_interrupt: Optional[Callable[[], bool]] = None,
        interval: float = 0.01,
    ) -> bool:
        while True:
            if self._is_interrupted(should_interrupt):
                return True

            remaining = target_time - time.perf_counter()
            if remaining <= 0:
                return False

            time.sleep(min(interval, remaining))

    def _transition_to(
        self,
        target_image: Image.Image,
        preview_name: Optional[str] = None,
        steps: int = 6,
        delay: float = 0.035,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        target = self._prepare_image(target_image)

        if self.last_frame is None:
            for i in range(1, steps + 1):
                cut = int(self.width * i / steps)
                frame = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
                frame.paste(target.crop((0, 0, cut, self.height)), (0, 0))
                self._push_prepared(frame)
                if self._sleep_with_interrupt(delay, should_interrupt):
                    self.last_frame = frame
                    return True
        else:
            for i in range(1, steps + 1):
                alpha = i / steps
                frame = Image.blend(self.last_frame, target, alpha)
                self._push_prepared(frame)
                if self._sleep_with_interrupt(delay, should_interrupt):
                    self.last_frame = frame
                    return True

        self._push_prepared(target)
        self._save_prepared(target, preview_name)
        self.last_frame = target
        return False

    def _new_canvas(self) -> Image.Image:
        return Image.new("RGBA", (self.width, self.height), DEFAULT_BG)

    def _new_overlay(self, width: int, height: int) -> Image.Image:
        return Image.new("RGBA", (width, height), (0, 0, 0, 0))

    def _download_image(self, url: Optional[str]) -> Optional[Image.Image]:
        if not url:
            return None

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "RaspberryPi-Pokemon-LED/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")

    def _fit_image(
        self,
        image: Image.Image,
        target_width: int,
        target_height: int,
        *,
        background=DEFAULT_BG,
    ) -> Image.Image:
        working = image.copy().convert("RGBA")
        working.thumbnail((target_width, target_height), Image.LANCZOS)
        canvas = Image.new("RGBA", (target_width, target_height), background)
        x = (target_width - working.width) // 2
        y = (target_height - working.height) // 2
        canvas.paste(working, (x, y), working)
        return canvas

    def _draw_line(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        fill=TEXT_PRIMARY,
        font=None,
    ) -> None:
        draw.text((x, y), text, font=font or self.font, fill=fill)

    def _draw_text_segments(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        segments: list[tuple[str, tuple[int, int, int, int]]],
        font=None,
    ) -> None:
        active_font = font or self.font
        cursor_x = x
        for text, fill in segments:
            if not text:
                continue
            draw.text((cursor_x, y), text, font=active_font, fill=fill)
            cursor_x += self._text_width(text, active_font)

    def _segments_width(
        self,
        segments: list[tuple[str, tuple[int, int, int, int]]],
        font=None,
    ) -> int:
        active_font = font or self.font
        return sum(self._text_width(text, active_font) for text, _ in segments if text)

    def _panel_bounds(self, index: int) -> tuple[int, int]:
        x0 = index * self.panel_width
        if index >= PANEL_CHAIN_LENGTH - 1:
            return x0, self.width - 1
        return x0, ((index + 1) * self.panel_width) - 1

    def _draw_panel_backgrounds(
        self,
        draw: ImageDraw.ImageDraw,
        *,
        top: int = 0,
        bottom: Optional[int] = None,
    ) -> None:
        bottom_edge = self.height - 1 if bottom is None else bottom
        for index in range(PANEL_CHAIN_LENGTH):
            x0, x1 = self._panel_bounds(index)
            fill = PANEL_FILL if index % 2 == 0 else PANEL_FILL_ALT
            draw.rectangle((x0, top, x1, bottom_edge), fill=fill)

        for divider_index in range(1, PANEL_CHAIN_LENGTH):
            divider_x = divider_index * self.panel_width
            draw.line((divider_x, top, divider_x, bottom_edge), fill=PANEL_DIVIDER)

    def _draw_text_centered(
        self, draw: ImageDraw.ImageDraw, lines: list[str], fill=TEXT_PRIMARY, font=None
    ) -> None:
        active_font = font or self.font
        active_line_height = self._get_line_height(active_font)
        total_height = len(lines) * active_line_height
        y = max(0, (self.height - total_height) // 2)

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=active_font)
            text_width = bbox[2] - bbox[0]
            x = max(0, (self.width - text_width) // 2)
            draw.text((x, y), line, font=active_font, fill=fill)
            y += active_line_height

    def _draw_repeating_ticker(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        y: int,
        offset_px: int,
        font=None,
        fill=TEXT_PRIMARY,
        x_start: int = 0,
    ) -> None:
        active_font = font or self.font
        ticker_width = self._text_width(text, active_font)
        if ticker_width <= 0:
            return

        loop_width = max(1, ticker_width)
        offset = offset_px % loop_width
        x = x_start - offset
        while x + ticker_width < x_start:
            x += loop_width

        while x < self.width:
            self._draw_line(draw, x, y, text, fill=fill, font=active_font)
            x += loop_width

    def _draw_repeating_ticker_segments(
        self,
        draw: ImageDraw.ImageDraw,
        segments: list[tuple[str, tuple[int, int, int, int]]],
        *,
        y: int,
        offset_px: int,
        font=None,
        x_start: int = 0,
    ) -> None:
        active_font = font or self.font
        loop_width = max(1, self._segments_width(segments, active_font))
        offset = offset_px % loop_width
        x = x_start - offset
        while x + loop_width < x_start:
            x += loop_width

        while x < self.width:
            self._draw_text_segments(draw, x, y, segments, font=active_font)
            x += loop_width

    def render_scrolling_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font=None,
        x: int = 0,
        y: int = 0,
        max_width: Optional[int] = None,
        fill=TEXT_PRIMARY,
        gap: int = 12,
        pause_frames: int = 8,
        step_px: int = 1,
    ) -> list[Image.Image]:
        active_font = font or self.font
        value = str(text)
        available_width = max_width if max_width is not None else max(0, self.width - x)
        available_width = min(available_width, max(0, self.width - x))

        if available_width <= 0 or y >= self.height:
            return []

        if not value:
            draw.text((x, y), value, font=active_font, fill=fill)
            return []

        text_width = self._text_width(value, active_font)
        if text_width <= available_width:
            draw.text((x, y), value, font=active_font, fill=fill)
            return []

        base_image = draw._image.copy()
        left, top, right, bottom = active_font.getbbox(value)
        text_height = max(1, bottom - top)
        draw_x = -left
        draw_y = -top
        region_height = min(self.height - y, text_height)
        gap = max(4, gap)
        step_px = max(1, step_px)

        loop_width = text_width + gap
        pause_offset = text_width - available_width
        offsets = list(range(0, loop_width, step_px))
        if offsets[-1] != pause_offset and pause_offset not in offsets:
            offsets.append(pause_offset)
            offsets.sort()

        frames: list[Image.Image] = []
        for offset in offsets:
            region = Image.new("RGBA", (available_width, region_height), (0, 0, 0, 0))
            region_draw = ImageDraw.Draw(region)
            region_draw.text(
                (draw_x - offset, draw_y), value, font=active_font, fill=fill
            )
            region_draw.text(
                (draw_x + loop_width - offset, draw_y),
                value,
                font=active_font,
                fill=fill,
            )

            frame = base_image.copy()
            frame.paste(region, (x, y), region)
            frames.append(frame)

            if offset == pause_offset:
                for _ in range(pause_frames):
                    frames.append(frame.copy())

        return frames

    def _draw_cloud(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        draw.ellipse((x + 2, y + 5, x + 10, y + 13), fill=ICON_MAIN)
        draw.ellipse((x + 8, y + 2, x + 16, y + 12), fill=ICON_MAIN)
        draw.ellipse((x + 14, y + 5, x + 22, y + 13), fill=ICON_MAIN)
        draw.rectangle((x + 5, y + 9, x + 19, y + 14), fill=ICON_MAIN)

    def _draw_sun(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        draw.ellipse((x + 5, y + 5, x + 15, y + 15), fill=ICON_ALT)
        draw.line((x + 10, y, x + 10, y + 4), fill=ICON_ALT)
        draw.line((x + 10, y + 16, x + 10, y + 20), fill=ICON_ALT)
        draw.line((x, y + 10, x + 4, y + 10), fill=ICON_ALT)
        draw.line((x + 16, y + 10, x + 20, y + 10), fill=ICON_ALT)

    def _draw_rain(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        self._draw_cloud(draw, x, y)
        draw.line((x + 7, y + 16, x + 5, y + 20), fill=ICON_ALT)
        draw.line((x + 12, y + 16, x + 10, y + 20), fill=ICON_ALT)
        draw.line((x + 17, y + 16, x + 15, y + 20), fill=ICON_ALT)

    def _draw_snow(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        self._draw_cloud(draw, x, y)
        for sx, sy in [(7, 18), (12, 19), (17, 18)]:
            draw.line((x + sx - 2, y + sy, x + sx + 2, y + sy), fill=ICON_ALT)
            draw.line((x + sx, y + sy - 2, x + sx, y + sy + 2), fill=ICON_ALT)

    def _draw_storm(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        self._draw_cloud(draw, x, y)
        draw.line((x + 12, y + 14, x + 9, y + 19), fill=ICON_ALT)
        draw.line((x + 9, y + 19, x + 13, y + 19), fill=ICON_ALT)
        draw.line((x + 13, y + 19, x + 10, y + 24), fill=ICON_ALT)

    def _draw_fog(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        draw.line((x + 2, y + 8, x + 22, y + 8), fill=ICON_MAIN)
        draw.line((x, y + 12, x + 20, y + 12), fill=ICON_MAIN)
        draw.line((x + 2, y + 16, x + 22, y + 16), fill=ICON_MAIN)

    def _draw_weather_icon(
        self, draw: ImageDraw.ImageDraw, condition: str, x: int, y: int
    ) -> None:
        c = condition.lower()
        if "thunder" in c or "storm" in c:
            self._draw_storm(draw, x, y)
        elif "snow" in c:
            self._draw_snow(draw, x, y)
        elif "rain" in c or "drizzle" in c or "shower" in c:
            self._draw_rain(draw, x, y)
        elif "fog" in c:
            self._draw_fog(draw, x, y)
        elif "cloud" in c or "overcast" in c:
            self._draw_cloud(draw, x, y)
        elif "clear" in c or "sun" in c:
            self._draw_sun(draw, x, y)
        else:
            self._draw_cloud(draw, x, y)

    def _render_pokemon_center_title(self, data: dict) -> Image.Image:
        img = self._new_overlay(self.panel_width, self.height)
        draw = ImageDraw.Draw(img)
        title_lines = ["Today's", "Pokémon is:"]
        title_block_height = len(title_lines) * self.small_line_height
        title_gap = 1
        name_area_height = max(1, self.height - title_block_height - title_gap)
        name = str(data.get("name", "Unknown"))
        name_max_width = self.panel_width - (PANEL_PADDING * 2)
        name_font_candidates = [
            self.large_font,
            self.medium_font,
            self.font,
            self.small_font,
        ]

        name_lines, name_font, truncated = self._fit_pokemon_name_lines(
            name,
            name_max_width,
            font_candidates=name_font_candidates,
            max_height_px=name_area_height,
        )

        show_label = True
        if truncated:
            retry_lines, retry_font, retry_truncated = self._fit_pokemon_name_lines(
                name,
                name_max_width,
                font_candidates=name_font_candidates,
                max_lines=4,
                max_height_px=self.height,
            )
            if not retry_truncated:
                name_lines = retry_lines
                name_font = retry_font
                show_label = False

        name_line_height = self._get_line_height(name_font)

        if show_label:
            total_height = (
                title_block_height + title_gap + (len(name_lines) * name_line_height)
            )
            y = max(0, (self.height - total_height) // 2)
            for title_line in title_lines:
                title_x = max(
                    0,
                    (self.panel_width - self._text_width(title_line, self.small_font))
                    // 2,
                )
                self._draw_line(
                    draw,
                    title_x,
                    y,
                    title_line,
                    fill=TEXT_ACCENT,
                    font=self.small_font,
                )
                y += self.small_line_height
            y += title_gap
        else:
            total_height = len(name_lines) * name_line_height
            y = max(0, (self.height - total_height) // 2)

        for line in name_lines:
            line_width = self._text_width(line, name_font)
            line_x = max(0, (self.panel_width - line_width) // 2)
            self._draw_line(
                draw,
                line_x,
                y,
                line,
                fill=POKEMON_NAME,
                font=name_font,
            )
            y += name_line_height
        return img

    def _render_pokemon_intro_card(self, data: dict) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        title_line = "Today's Pokémon is:"
        title_gap = 2
        title_font = self.small_font
        title_height = self.small_line_height
        name_area_height = max(1, self.height - title_height - title_gap)

        name_lines, name_font, _ = self._fit_pokemon_name_lines(
            str(data.get("name", "Unknown")),
            self.width - (PANEL_PADDING * 2),
            font_candidates=[
                self.hero_font,
                self.large_font,
                self.medium_font,
                self.font,
                self.small_font,
            ],
            max_height_px=name_area_height,
        )
        name_line_height = self._get_line_height(name_font)
        total_height = title_height + title_gap + (len(name_lines) * name_line_height)
        y = max(0, (self.height - total_height) // 2)

        title_x = max(0, (self.width - self._text_width(title_line, title_font)) // 2)
        self._draw_line(
            draw,
            title_x,
            y,
            title_line,
            fill=TEXT_ACCENT,
            font=title_font,
        )
        y += title_height + title_gap

        for line in name_lines:
            line_width = self._text_width(line, name_font)
            line_x = max(0, (self.width - line_width) // 2)
            self._draw_line(
                draw,
                line_x,
                y,
                line,
                fill=POKEMON_NAME,
                font=name_font,
            )
            y += name_line_height
        return img

    def _pokemon_artwork(self, data: dict) -> Optional[Image.Image]:
        art = None
        try:
            art = self._download_image(data.get("image_url"))
        except Exception:
            art = None
        return art

    def _fit_pokemon_name_lines(
        self,
        name: str,
        max_width_px: int,
        *,
        font_candidates: Optional[list] = None,
        max_lines: int = 2,
        max_height_px: Optional[int] = None,
    ):
        candidates = font_candidates or [self.medium_font, self.font]
        for candidate_font in candidates:
            lines = self._wrap_text(name, max_width_px, font=candidate_font)
            line_height = self._get_line_height(candidate_font)
            if len(lines) <= max_lines and (
                max_height_px is None or (len(lines) * line_height) <= max_height_px
            ):
                return lines, candidate_font, False

        fallback_font = candidates[-1]
        truncated = self._truncate_to_width(name, max_width_px, font=fallback_font)
        if (
            max_height_px is not None
            and self._get_line_height(fallback_font) > max_height_px
        ):
            return [""], fallback_font, True
        return [truncated], fallback_font, True

    def _render_pokemon_stat_frame(
        self,
        label: str,
        value: str,
        *,
        value_fill=TEXT_PRIMARY,
    ) -> Image.Image:
        img = self._new_overlay(self.panel_width, self.height)
        draw = ImageDraw.Draw(img)
        label_text = self._truncate_to_width(
            label,
            self.panel_width - (PANEL_PADDING * 2),
            font=self.small_font,
        )
        label_height = self.small_line_height
        value_gap = 2

        value_lines, value_font, _ = self._fit_pokemon_name_lines(
            value,
            self.panel_width - (PANEL_PADDING * 2),
            font_candidates=[self.medium_font, self.font, self.small_font],
            max_height_px=max(1, self.height - label_height - value_gap),
        )
        value_line_height = self._get_line_height(value_font)
        total_height = label_height + value_gap + (len(value_lines) * value_line_height)
        label_y = max(0, (self.height - total_height) // 2)
        self._draw_line(
            draw,
            max(
                0,
                (self.panel_width - self._text_width(label_text, self.small_font)) // 2,
            ),
            label_y,
            label_text,
            fill=POKEMON_STAT_LABEL,
            font=self.small_font,
        )
        value_y = label_y + label_height + value_gap
        for line in value_lines:
            line_width = self._text_width(line, value_font)
            line_x = max(0, (self.panel_width - line_width) // 2)
            self._draw_line(
                draw,
                line_x,
                value_y,
                line,
                fill=value_fill,
                font=value_font,
            )
            value_y += value_line_height
        return img

    def _render_pokemon_image_frame(self, data: dict) -> Image.Image:
        img = self._new_overlay(self.panel_width, self.height)
        art = self._pokemon_artwork(data)
        if art is None:
            return img

        fitted_art = self._fit_image(
            art,
            self.panel_width - 4,
            self.height - 2,
            background=(0, 0, 0, 0),
        )
        art_x = (self.panel_width - fitted_art.width) // 2
        art_y = (self.height - fitted_art.height) // 2
        img.paste(fitted_art, (art_x, art_y), fitted_art)
        return img

    def _compose_pokemon_frame(
        self,
        *,
        name_panel: Optional[Image.Image] = None,
        stat_panel: Optional[Image.Image] = None,
        image_panel: Optional[Image.Image] = None,
    ) -> Image.Image:
        img = self._new_canvas()
        panels = (
            (0, name_panel),
            (self.panel_width, stat_panel),
            (self.panel_width * 2, image_panel),
        )
        for x_offset, panel in panels:
            if panel is not None:
                img.paste(panel, (x_offset, 0), panel)
        return img

    def _scale_image_alpha(self, image: Image.Image, factor: float) -> Image.Image:
        if factor <= 0:
            return self._new_overlay(image.width, image.height)
        if factor >= 1:
            return image

        faded = image.copy()
        alpha = faded.getchannel("A").point(lambda value: int(value * factor))
        faded.putalpha(alpha)
        return faded

    def _pokemon_stat_frames(self, data: dict) -> list[Image.Image]:
        stat_entries = [
            (
                "Type",
                " / ".join(str(value) for value in data.get("types", []) if value)
                or "Unknown",
                POKEMON_NAME,
            ),
            ("HP", str(data.get("hp", "--")), TEXT_PRIMARY),
            ("Attack", str(data.get("attack", "--")), TEXT_PRIMARY),
            ("Defense", str(data.get("defense", "--")), TEXT_PRIMARY),
        ]
        return [
            self._render_pokemon_stat_frame(label, value, value_fill=fill)
            for label, value, fill in stat_entries
        ]

    def _render_pokemon_base(self, data: dict) -> Image.Image:
        stat_frames = self._pokemon_stat_frames(data)
        return self._compose_pokemon_frame(
            name_panel=self._render_pokemon_center_title(data),
            stat_panel=stat_frames[0] if stat_frames else None,
            image_panel=self._render_pokemon_image_frame(data),
        )

    def render_weather(self, payload: dict) -> Image.Image:
        ticker = self._build_weather_ticker(payload["data"])
        frame_time = datetime.now()
        base_frame = self._render_weather_static_frame(payload, frame_time=frame_time)
        return self._weather_ticker_frame(
            payload,
            ticker,
            offset_px=0,
            frame_time=frame_time,
            base_frame=base_frame,
        )

    def _render_joke_page(
        self,
        label: str,
        lines: list[str],
        *,
        fill=TEXT_PRIMARY,
        label_fill=JOKE_LABEL,
        font=None,
    ) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_text_centered(
            draw, lines, fill=fill, font=font or self.medium_font
        )
        return img

    def _paginate_lines(self, lines: list[str], max_lines: int = 3) -> list[list[str]]:
        pages = [lines[i : i + max_lines] for i in range(0, len(lines), max_lines)]
        return pages or [[""]]

    def _fit_joke_lines(
        self,
        text: str,
        *,
        max_width_px: int,
        max_height_px: int,
    ):
        candidates = [self.medium_font, self.font, self.small_font]
        last_lines: list[str] = [""]
        last_font = candidates[-1]
        for candidate_font in candidates:
            lines = self._wrap_text(text, max_width_px, font=candidate_font)
            line_height = self._get_line_height(candidate_font)
            last_lines, last_font = lines, candidate_font
            if len(lines) * line_height <= max_height_px:
                return lines, candidate_font, True
        return last_lines, last_font, False

    def _build_joke_segment_pages(
        self,
        text: str,
        label: str,
        *,
        fill=TEXT_PRIMARY,
        label_fill=JOKE_LABEL,
    ) -> list[Image.Image]:
        max_width = self.width - 12
        max_height = self.height
        lines, font, fits = self._fit_joke_lines(
            text or "",
            max_width_px=max_width,
            max_height_px=max_height,
        )
        if fits:
            return [
                self._render_joke_page(
                    label, lines, fill=fill, label_fill=label_fill, font=font
                )
            ]
        line_height = self._get_line_height(font)
        max_lines_per_page = max(1, max_height // line_height)
        pages = self._paginate_lines(lines, max_lines=max_lines_per_page)
        return [
            self._render_joke_page(
                label, page, fill=fill, label_fill=label_fill, font=font
            )
            for page in pages
        ]

    def _build_joke_pages(self, text: str, fill=TEXT_PRIMARY) -> list[Image.Image]:
        return self._build_joke_segment_pages(text, "JOKE", fill=fill)

    def render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]
        if data.get("type") == "twopart":
            setup_pages = self._build_joke_segment_pages(
                data.get("setup") or "",
                "SETUP",
                fill=TEXT_PRIMARY,
            )
            delivery_pages = self._build_joke_segment_pages(
                data.get("delivery") or "",
                "PUNCHLINE",
                fill=JOKE_DELIVERY,
                label_fill=JOKE_DELIVERY,
            )
            return setup_pages + delivery_pages
        return self._build_joke_pages(data.get("text") or "No joke", fill=TEXT_PRIMARY)

    def render_science(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        name = self._truncate_to_width(
            str(data.get("name", "Unknown")), self.width - 4, font=self.small_font
        )
        symbol = self._truncate_to_width(
            f"({data.get('symbol', '?')})", self.width - 4, font=self.small_font
        )
        atomic_number = data.get("atomic_number", "?")
        atomic_line = self._truncate_to_width(
            f"Atomic {atomic_number}", self.width - 4, font=self.small_font
        )

        self._draw_text_centered(
            draw, [name, symbol, atomic_line], fill=TEXT_PRIMARY, font=self.small_font
        )
        return img

    def render_snake_message(self, lines: list[str]) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        active_lines: list[str] = []
        active_font = self.font
        for candidate_font in (self.font, self.small_font):
            candidate_lines: list[str] = []
            for line in lines:
                candidate_lines.extend(
                    self._wrap_text(
                        str(line),
                        width_px=self.width - 8,
                        font=candidate_font,
                    )
                )
            line_height = self._get_line_height(candidate_font)
            active_lines = candidate_lines
            active_font = candidate_font
            if len(candidate_lines) * line_height <= self.height:
                break
        self._draw_text_centered(
            draw,
            active_lines or ["Snake Game"],
            fill=SNAKE_TEXT,
            font=active_font,
        )
        return img

    def _scale_rgba(
        self,
        fill: tuple[int, int, int, int],
        factor: float,
    ) -> tuple[int, int, int, int]:
        clamped = max(0.0, min(1.25, float(factor)))
        red, green, blue, alpha = fill
        return (
            min(255, int(red * clamped)),
            min(255, int(green * clamped)),
            min(255, int(blue * clamped)),
            alpha,
        )

    def render_snake_game(self, snapshot) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        cell_size = max(1, int(getattr(snapshot, "cell_size", 2)))
        pulse_factor = max(0.0, float(getattr(snapshot, "pulse_factor", 1.0)))
        body_fill = self._scale_rgba(SNAKE_BODY, pulse_factor)
        head_fill = self._scale_rgba(SNAKE_HEAD, pulse_factor)
        playfield_bounds = getattr(snapshot, "playfield_bounds", None)
        if playfield_bounds:
            play_left, play_top, play_right, play_bottom = [
                int(value) for value in playfield_bounds
            ]
        else:
            play_left = 0
            play_top = 0
            play_right = int(getattr(snapshot, "grid_width", self.width)) - 1
            play_bottom = int(getattr(snapshot, "grid_height", self.height)) - 1
        score_text = str(max(0, int(getattr(snapshot, "score", 0))))
        overlay_cells = getattr(snapshot, "score_overlay_cells", None)
        if overlay_cells:
            overlay_width = int(overlay_cells[0]) * cell_size
            overlay_height = int(overlay_cells[1]) * cell_size
        else:
            overlay_width = self._text_width(score_text, font=self.small_font) + 4
            overlay_height = self.small_line_height + 1
        overlay_width = max(1, min(self.width, overlay_width))
        overlay_height = max(1, min(self.height, overlay_height))
        draw.rectangle(
            (0, 0, overlay_width - 1, overlay_height - 1),
            fill=DEFAULT_BG,
        )
        hud_notch_cells = getattr(snapshot, "hud_notch_cells", None)

        def is_hud_notch_cell(cell_x: int, cell_y: int) -> bool:
            if not hud_notch_cells:
                return False
            notch_right_cell, notch_bottom_cell = [
                int(value) for value in hud_notch_cells
            ]
            return (
                play_left <= cell_x < notch_right_cell
                and play_top <= cell_y < notch_bottom_cell
            )

        def is_playfield_cell(cell_x: int, cell_y: int) -> bool:
            return (
                play_left <= cell_x <= play_right
                and play_top <= cell_y <= play_bottom
                and not is_hud_notch_cell(cell_x, cell_y)
            )

        border_left = max(0, (play_left * cell_size) - 1)
        border_top = max(0, (play_top * cell_size) - 1)
        border_right = min(self.width - 1, ((play_right + 1) * cell_size))
        border_bottom = min(self.height - 1, ((play_bottom + 1) * cell_size))
        if hud_notch_cells:
            notch_right_cell, notch_bottom_cell = [
                int(value) for value in hud_notch_cells
            ]
            notch_right = max(
                border_left,
                min(border_right, (notch_right_cell * cell_size) - 1),
            )
            notch_bottom = max(
                border_top,
                min(border_bottom, (notch_bottom_cell * cell_size) - 1),
            )
            draw.line(
                (border_left, notch_bottom, border_left, border_bottom),
                fill=SNAKE_BORDER,
            )
            draw.line(
                (border_left, border_bottom, border_right, border_bottom),
                fill=SNAKE_BORDER,
            )
            draw.line(
                (border_right, border_top, border_right, border_bottom),
                fill=SNAKE_BORDER,
            )
            draw.line(
                (notch_right, border_top, border_right, border_top), fill=SNAKE_BORDER
            )
            draw.line(
                (notch_right, border_top, notch_right, notch_bottom), fill=SNAKE_BORDER
            )
            draw.line(
                (border_left, notch_bottom, notch_right, notch_bottom),
                fill=SNAKE_BORDER,
            )
        else:
            draw.rectangle(
                (border_left, border_top, border_right, border_bottom),
                outline=SNAKE_BORDER,
            )

        for cell_x, cell_y in getattr(snapshot, "obstacles", []):
            if not is_playfield_cell(cell_x, cell_y):
                continue
            draw.rectangle(
                (
                    cell_x * cell_size,
                    cell_y * cell_size,
                    ((cell_x + 1) * cell_size) - 1,
                    ((cell_y + 1) * cell_size) - 1,
                ),
                fill=SNAKE_OBSTACLE,
            )

        food_x, food_y = snapshot.food
        if is_playfield_cell(food_x, food_y):
            draw.rectangle(
                (
                    food_x * cell_size,
                    food_y * cell_size,
                    ((food_x + 1) * cell_size) - 1,
                    ((food_y + 1) * cell_size) - 1,
                ),
                fill=SNAKE_FOOD,
            )

        for index, (cell_x, cell_y) in enumerate(reversed(snapshot.snake)):
            if not is_playfield_cell(cell_x, cell_y):
                continue
            fill = head_fill if index == len(snapshot.snake) - 1 else body_fill
            draw.rectangle(
                (
                    cell_x * cell_size,
                    cell_y * cell_size,
                    ((cell_x + 1) * cell_size) - 1,
                    ((cell_y + 1) * cell_size) - 1,
                ),
                fill=fill,
            )
        score_text = self._truncate_to_width(
            score_text,
            max(1, overlay_width - 1),
            font=self.small_font,
        )
        self._draw_line(draw, 1, 0, score_text, fill=SNAKE_TEXT, font=self.small_font)
        return img

    def _draw_custom_text_line(
        self,
        draw: ImageDraw.ImageDraw,
        line: str,
        *,
        y: int,
        x_start: int,
        max_width: int,
        font,
        fill,
        alignment: str,
        underline: bool,
        is_last_line: bool,
    ) -> None:
        if not line:
            return

        text_width = self._text_width(line, font=font)
        if alignment == "center":
            x = x_start + max(0, (max_width - text_width) // 2)
            draw.text((x, y), line, font=font, fill=fill)
            underline_start = x
            underline_end = x + text_width
        elif alignment == "right":
            x = x_start + max(0, max_width - text_width)
            draw.text((x, y), line, font=font, fill=fill)
            underline_start = x
            underline_end = x + text_width
        elif alignment == "justify" and not is_last_line:
            words = [word for word in line.split(" ") if word]
            if len(words) <= 1:
                draw.text((x_start, y), line, font=font, fill=fill)
                underline_start = x_start
                underline_end = x_start + text_width
            else:
                words_width = sum(self._text_width(word, font=font) for word in words)
                gap_count = len(words) - 1
                total_gap_width = max(0, max_width - words_width)
                gap_width = total_gap_width // gap_count if gap_count > 0 else 0
                remainder = total_gap_width - (gap_width * gap_count)
                cursor_x = x_start
                underline_start = x_start
                underline_end = x_start
                for index, word in enumerate(words):
                    word_width = self._text_width(word, font=font)
                    draw.text((cursor_x, y), word, font=font, fill=fill)
                    underline_end = cursor_x + word_width
                    cursor_x += word_width
                    if index < gap_count:
                        cursor_x += gap_width + (1 if index < remainder else 0)
        else:
            draw.text((x_start, y), line, font=font, fill=fill)
            underline_start = x_start
            underline_end = x_start + text_width

        if underline:
            underline_y = min(self.height - 1, y + self._get_line_height(font) - 2)
            draw.line(
                (underline_start, underline_y, underline_end, underline_y), fill=fill
            )

    def _build_custom_text_pages(self, payload: dict):
        data = payload["data"]
        style = data.get("style") or {}
        text = str(data.get("text") or "")
        x_padding = 4
        y_padding = 2
        max_width = max(1, self.width - (x_padding * 2))
        max_height = max(1, self.height - (y_padding * 2))

        requested_size = max(8, int(style.get("font_size", 16)))
        font = self._load_styled_font(
            requested_size,
            family=style.get("font_family", "sans"),
            bold=bool(style.get("bold")),
            italic=bool(style.get("italic")),
        )
        line_height = self._get_line_height(font)
        max_lines = max(1, max_height // line_height)
        lines = self._wrap_text(text, width_px=max_width, font=font)

        while requested_size > 8 and len(lines) > max_lines:
            requested_size -= 1
            font = self._load_styled_font(
                requested_size,
                family=style.get("font_family", "sans"),
                bold=bool(style.get("bold")),
                italic=bool(style.get("italic")),
            )
            line_height = self._get_line_height(font)
            max_lines = max(1, max_height // line_height)
            lines = self._wrap_text(text, width_px=max_width, font=font)

        pages = self._paginate_lines(lines, max_lines=max_lines)
        return pages, font

    def render_custom_text_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]
        style = data.get("style") or {}
        pages, font = self._build_custom_text_pages(payload)
        text_fill = self._scale_custom_text_fill(
            self._custom_text_color(style.get("text_color"), TEXT_PRIMARY),
            style.get("text_brightness", style.get("brightness", 100)),
        )
        background_fill = self._scale_custom_text_fill(
            self._custom_text_color(style.get("background_color"), DEFAULT_BG),
            style.get("background_brightness", style.get("brightness", 100)),
        )
        x_padding = 4
        max_width = max(1, self.width - (x_padding * 2))
        alignment = str(style.get("alignment", "center")).lower()
        underline = bool(style.get("underline"))
        line_height = self._get_line_height(font)

        rendered_pages: list[Image.Image] = []
        for lines in pages:
            img = Image.new("RGBA", (self.width, self.height), background_fill)
            draw = ImageDraw.Draw(img)
            total_height = len(lines) * line_height
            y = max(0, (self.height - total_height) // 2)

            for index, line in enumerate(lines):
                self._draw_custom_text_line(
                    draw,
                    line,
                    y=y,
                    x_start=x_padding,
                    max_width=max_width,
                    font=font,
                    fill=text_fill,
                    alignment=alignment,
                    underline=underline,
                    is_last_line=index == len(lines) - 1,
                )
                y += line_height

            rendered_pages.append(img)

        return rendered_pages or [
            Image.new("RGBA", (self.width, self.height), background_fill)
        ]

    def render_payload(self, payload: dict) -> Image.Image:
        category = payload["category"]
        if category == "pokemon":
            return self._render_pokemon_base(payload["data"])
        if category == "weather":
            return self.render_weather(payload)
        if category == "joke":
            return self.render_joke_pages(payload)[0]
        if category == "science":
            return self.render_science(payload)
        if category == "custom_text":
            return self.render_custom_text_pages(payload)[0]

        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_line(draw, 2, 12, "UNKNOWN", fill=TEXT_PRIMARY, font=self.small_font)
        return img

    def _fade_sequence(
        self,
        image: Image.Image,
        steps: int = 6,
        fade_in: bool = True,
        delay: float = 0.05,
        should_interrupt: Optional[Callable[[], bool]] = None,
        end_time: Optional[float] = None,
    ) -> bool:
        factors = (
            [i / steps for i in range(1, steps + 1)]
            if fade_in
            else [i / steps for i in range(steps - 1, -1, -1)]
        )
        for factor in factors:
            if end_time is not None and time.time() >= end_time:
                return False
            frame = Image.blend(self._new_canvas(), image, factor)
            self._show_frame(frame)
            sleep_for = delay
            if end_time is not None:
                sleep_for = min(delay, max(0.0, end_time - time.time()))
            if sleep_for > 0 and self._sleep_with_interrupt(
                sleep_for, should_interrupt
            ):
                return True
        return False

    def _fade_pokemon_stat_panel(
        self,
        *,
        name_panel: Image.Image,
        stat_panel: Image.Image,
        image_panel: Image.Image,
        steps: int = 5,
        fade_in: bool = True,
        delay: float = 0.04,
        should_interrupt: Optional[Callable[[], bool]] = None,
        end_time: Optional[float] = None,
    ) -> bool:
        factors = (
            [i / steps for i in range(1, steps + 1)]
            if fade_in
            else [i / steps for i in range(steps - 1, -1, -1)]
        )
        for factor in factors:
            if end_time is not None and time.time() >= end_time:
                return False
            frame = self._compose_pokemon_frame(
                name_panel=name_panel,
                stat_panel=self._scale_image_alpha(stat_panel, factor),
                image_panel=image_panel,
            )
            self._show_frame(frame)
            sleep_for = delay
            if end_time is not None:
                sleep_for = min(delay, max(0.0, end_time - time.time()))
            if sleep_for > 0 and self._sleep_with_interrupt(
                sleep_for, should_interrupt
            ):
                return True
        return False

    def _pokemon_intro_phase_durations(self, total_duration: float) -> dict[str, float]:
        phase_targets = {
            "fade_out_previous": 0.35,
            "intro_fade_in": 0.40,
            "intro_hold": 1.00,
            "intro_fade_out": 0.40,
            "content_fade_in": 0.35,
        }
        reserved_content_time = min(0.75, max(0.25, total_duration * 0.25))
        available_intro_time = max(0.0, total_duration - reserved_content_time)
        target_total = sum(phase_targets.values())
        scale = (
            min(1.0, available_intro_time / target_total) if target_total > 0 else 0.0
        )
        return {
            phase_name: phase_duration * scale
            for phase_name, phase_duration in phase_targets.items()
        }

    def _animate_custom_text(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        pages = self.render_custom_text_pages(payload)
        end_time = time.time() + max(1, duration_seconds)

        if self._transition_to(
            pages[0],
            preview_name=f"{safe_slot}_custom_text_0.png",
            steps=5,
            delay=0.03,
            should_interrupt=should_interrupt,
        ):
            return True

        page_index = 0
        while time.time() < end_time:
            if self._is_interrupted(should_interrupt):
                return True

            page = pages[page_index % len(pages)]
            self._show_frame(
                page,
                preview_name=f"{safe_slot}_custom_text_{page_index % len(pages)}.png",
            )
            page_duration = min(2.5, max(0.2, end_time - time.time()))
            if self._sleep_with_interrupt(page_duration, should_interrupt):
                return True
            page_index += 1
        return False

    def _animate_pokemon(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        data = payload["data"]
        total_duration = max(1.0, float(duration_seconds))
        end_time = time.time() + total_duration
        phase_durations = self._pokemon_intro_phase_durations(total_duration)

        name_panel = self._render_pokemon_center_title(data)
        image_panel = self._render_pokemon_image_frame(data)
        stat_frames = self._pokemon_stat_frames(data)
        intro = self._render_pokemon_intro_card(data)
        content_frame = self._compose_pokemon_frame(
            name_panel=name_panel,
            stat_panel=stat_frames[0] if stat_frames else None,
            image_panel=image_panel,
        )

        def remaining_time() -> float:
            return max(0.0, end_time - time.time())

        def phase_time(name: str) -> float:
            return min(phase_durations[name], remaining_time())

        fade_out_previous = phase_time("fade_out_previous")
        if fade_out_previous > 0 and self.last_frame is not None:
            if self._transition_to(
                self._new_canvas(),
                steps=6,
                delay=fade_out_previous / 6,
                should_interrupt=should_interrupt,
            ):
                return True

        intro_fade_in = phase_time("intro_fade_in")
        if intro_fade_in > 0:
            if self._fade_sequence(
                intro,
                steps=6,
                fade_in=True,
                delay=intro_fade_in / 6,
                should_interrupt=should_interrupt,
                end_time=time.time() + intro_fade_in,
            ):
                return True
            if self.last_frame is not None:
                self._save_prepared(
                    self.last_frame,
                    preview_name=f"{safe_slot}_pokemon_intro.png",
                )

        intro_hold = phase_time("intro_hold")
        if intro_hold > 0 and self._sleep_with_interrupt(intro_hold, should_interrupt):
            return True

        intro_fade_out = phase_time("intro_fade_out")
        if intro_fade_out > 0:
            if self._fade_sequence(
                intro,
                steps=6,
                fade_in=False,
                delay=intro_fade_out / 6,
                should_interrupt=should_interrupt,
                end_time=time.time() + intro_fade_out,
            ):
                return True

        if time.time() >= end_time or self._is_interrupted(should_interrupt):
            return self._is_interrupted(should_interrupt)

        content_fade_in = phase_time("content_fade_in")
        if content_fade_in > 0:
            if self._transition_to(
                content_frame,
                preview_name=f"{safe_slot}_pokemon_image.png",
                steps=6,
                delay=content_fade_in / 6,
                should_interrupt=should_interrupt,
            ):
                return True
        else:
            self._show_frame(
                content_frame,
                preview_name=f"{safe_slot}_pokemon_image.png",
            )

        remaining_after_transition = remaining_time()
        stats_end_time = time.time() + (remaining_after_transition * 0.65)
        stat_index = 1 if len(stat_frames) > 1 else 0
        final_frame = content_frame
        while stat_frames and time.time() < stats_end_time:
            if self._is_interrupted(should_interrupt):
                return True

            stat_panel = stat_frames[stat_index % len(stat_frames)]
            final_frame = self._compose_pokemon_frame(
                name_panel=name_panel,
                stat_panel=stat_panel,
                image_panel=image_panel,
            )
            if self._fade_pokemon_stat_panel(
                name_panel=name_panel,
                stat_panel=stat_panel,
                image_panel=image_panel,
                steps=5,
                fade_in=True,
                delay=0.04,
                should_interrupt=should_interrupt,
                end_time=stats_end_time,
            ):
                return True

            hold_time = min(0.75, max(0.0, stats_end_time - time.time()))
            if hold_time > 0 and self._sleep_with_interrupt(
                hold_time, should_interrupt
            ):
                return True

            if self._fade_pokemon_stat_panel(
                name_panel=name_panel,
                stat_panel=stat_panel,
                image_panel=image_panel,
                steps=5,
                fade_in=False,
                delay=0.04,
                should_interrupt=should_interrupt,
                end_time=stats_end_time,
            ):
                return True
            stat_index += 1

        if time.time() >= end_time:
            return False

        self._show_frame(final_frame, preview_name=f"{safe_slot}_pokemon_image.png")

        remaining = max(0.0, end_time - time.time())
        if remaining > 0:
            return self._sleep_with_interrupt(remaining, should_interrupt)
        return False

    def _animate_joke(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        data = payload["data"]
        end_time = time.time() + max(1, duration_seconds)

        segments: list[list[Image.Image]] = []
        if data.get("type") == "twopart":
            segments.append(
                self._build_joke_segment_pages(
                    data.get("setup") or "",
                    "SETUP",
                    fill=TEXT_PRIMARY,
                )
            )
            segments.append(
                self._build_joke_segment_pages(
                    data.get("delivery") or "",
                    "PUNCHLINE",
                    fill=JOKE_DELIVERY,
                    label_fill=JOKE_DELIVERY,
                )
            )
        else:
            segments.append(
                self._build_joke_pages(data.get("text") or "No joke", fill=TEXT_PRIMARY)
            )

        seg_idx = 0
        while time.time() < end_time:
            if self._is_interrupted(should_interrupt):
                return True

            pages = segments[seg_idx % len(segments)]
            first = pages[0]
            if self._transition_to(
                first,
                preview_name=f"{safe_slot}_joke_{seg_idx}_0.png",
                steps=6,
                delay=0.03,
                should_interrupt=should_interrupt,
            ):
                return True

            hold_end = min(end_time, time.time() + 10.0)
            page_idx = 0
            while time.time() < hold_end:
                page = pages[page_idx % len(pages)]
                self._show_frame(
                    page, preview_name=f"{safe_slot}_joke_{seg_idx}_{page_idx}.png"
                )
                page_duration = min(2.0, max(0.2, hold_end - time.time()))
                if self._sleep_with_interrupt(page_duration, should_interrupt):
                    return True
                page_idx += 1

            if self._fade_sequence(
                pages[min(page_idx - 1, len(pages) - 1)],
                steps=7,
                fade_in=False,
                delay=0.05,
                should_interrupt=should_interrupt,
            ):
                return True
            seg_idx += 1
        return False

    def _weather_temperature_fill(self, temperature) -> tuple[int, int, int, int]:
        try:
            if float(temperature) <= 45:
                return WEATHER_TEMP_COLD
        except (TypeError, ValueError):
            pass
        return WEATHER_TEMP_WARM

    def _build_weather_ticker(self, data: dict) -> str:
        condition = str(data.get("condition", "Unknown"))
        temp = str(data.get("temperature_f", "--"))
        wind = str(data.get("wind_mph", "--"))
        location = str(data.get("location", ""))
        return f"{location} | {condition} | {temp}F | Wind {wind} mph   |   "

    def _weather_condition_fill(self, condition: str) -> tuple[int, int, int, int]:
        lowered = condition.lower()
        if "rain" in lowered or "drizzle" in lowered or "shower" in lowered:
            return WEATHER_CONDITION_RAIN
        if "cloud" in lowered or "overcast" in lowered or "fog" in lowered:
            return WEATHER_CONDITION_CLOUDY
        if "clear" in lowered or "sun" in lowered:
            return WEATHER_CONDITION_SUNNY
        return WEATHER_TICKER

    def _weather_date_text(
        self,
        payload: dict | None = None,
        *,
        frame_time: datetime | None = None,
    ) -> str:
        current = frame_time or datetime.now()
        return current.strftime("%b %d, %Y")

    def _weather_time_text(self, *, frame_time: datetime | None = None) -> str:
        current = frame_time or datetime.now()
        time_text = current.strftime("%I:%M:%S %p")
        return time_text.lstrip("0") or time_text

    def _weather_header_key(self, *, frame_time: datetime | None = None) -> str:
        current = frame_time or datetime.now()
        return current.strftime("%Y-%m-%d %H:%M:%S")

    def _build_weather_ticker_segments(
        self, data: dict
    ) -> list[tuple[str, tuple[int, int, int, int]]]:
        condition = str(data.get("condition", "Unknown"))
        temp = str(data.get("temperature_f", "--"))
        wind = str(data.get("wind_mph", "--"))
        location = str(data.get("location", ""))
        divider = (" | ", TEXT_SECONDARY)
        return [
            (location, WEATHER_TICKER),
            divider,
            (condition, self._weather_condition_fill(condition)),
            divider,
            (f"{temp}F", WEATHER_TICKER),
            divider,
            (f"Wind {wind} mph", WEATHER_TICKER),
            ("   |   ", TEXT_SECONDARY),
        ]

    def _draw_weather_divider(self, draw: ImageDraw.ImageDraw, offset_px: int) -> None:
        divider_y = WEATHER_HEADER_HEIGHT
        draw.line((0, divider_y, self.width - 1, divider_y), fill=PANEL_DIVIDER)

    def _draw_weather_header(
        self,
        draw: ImageDraw.ImageDraw,
        payload: dict,
        offset_px: int,
        *,
        frame_time: datetime | None = None,
    ) -> None:
        data = payload["data"]
        condition = str(data.get("condition", "Unknown"))
        date_text = self._truncate_to_width(
            self._weather_date_text(payload, frame_time=frame_time),
            self.width - 42,
            font=self.small_font,
        )
        time_text = self._truncate_to_width(
            self._weather_time_text(frame_time=frame_time),
            self.width - 42,
            font=self.small_font,
        )
        self._draw_weather_icon(draw, condition, 4, 1)
        self._draw_line(
            draw,
            30,
            2,
            date_text,
            fill=TEXT_ACCENT,
            font=self.small_font,
        )
        self._draw_line(
            draw,
            30,
            10,
            time_text,
            fill=TEXT_PRIMARY,
            font=self.small_font,
        )
        self._draw_weather_divider(draw, offset_px)

    def _render_weather_static_frame(
        self,
        payload: dict,
        *,
        frame_time: datetime | None = None,
    ) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_weather_header(draw, payload, offset_px=0, frame_time=frame_time)
        return img

    def _weather_ticker_frame(
        self,
        payload: dict,
        ticker: str,
        offset_px: int,
        *,
        frame_time: datetime | None = None,
        base_frame: Image.Image | None = None,
        ticker_segments: list[tuple[str, tuple[int, int, int, int]]] | None = None,
    ) -> Image.Image:
        img = (
            base_frame.copy()
            if base_frame is not None
            else self._render_weather_static_frame(
                payload,
                frame_time=frame_time,
            )
        )
        draw = ImageDraw.Draw(img)
        self._draw_repeating_ticker_segments(
            draw,
            ticker_segments or self._build_weather_ticker_segments(payload["data"]),
            y=WEATHER_TICKER_Y,
            offset_px=offset_px,
            font=self.font,
        )
        return img

    def _animate_weather_ticker(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        ticker = self._build_weather_ticker(payload["data"])
        ticker_segments = self._build_weather_ticker_segments(payload["data"])
        end_time = time.perf_counter() + max(1.0, float(duration_seconds))
        loop_width = max(1, self._segments_width(ticker_segments, font=self.font))
        offset_px = 0
        frame_time = datetime.now()
        header_key = self._weather_header_key(frame_time=frame_time)
        base_frame = self._render_weather_static_frame(payload, frame_time=frame_time)

        first = self._weather_ticker_frame(
            payload,
            ticker,
            offset_px,
            frame_time=frame_time,
            base_frame=base_frame,
            ticker_segments=ticker_segments,
        )
        if self._transition_to(
            first,
            preview_name=f"{safe_slot}_weather.png",
            steps=6,
            delay=0.03,
            should_interrupt=should_interrupt,
        ):
            return True

        frame_start_time = time.perf_counter()
        frame_index = 1

        while time.perf_counter() < end_time:
            if self._is_interrupted(should_interrupt):
                return True

            next_frame_time = min(
                end_time,
                frame_start_time + (frame_index * WEATHER_TICKER_FRAME_DELAY),
            )
            if self._sleep_until(next_frame_time, should_interrupt):
                return True
            if time.perf_counter() >= end_time:
                break

            offset_px = frame_index % loop_width
            frame_time = datetime.now()
            next_header_key = self._weather_header_key(frame_time=frame_time)
            if next_header_key != header_key:
                base_frame = self._render_weather_static_frame(
                    payload,
                    frame_time=frame_time,
                )
                header_key = next_header_key

            frame = self._weather_ticker_frame(
                payload,
                ticker,
                offset_px,
                frame_time=frame_time,
                base_frame=base_frame,
                ticker_segments=ticker_segments,
            )
            self._show_frame(frame, preview_name=f"{safe_slot}_weather.png")
            frame_index += 1
        return False

    def display_payload(
        self,
        payload: dict,
        duration_seconds: Optional[int] = None,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        category = payload["category"]
        safe_slot = payload["slot_key"].replace(":", "-")
        total_duration = (
            duration_seconds if duration_seconds is not None else ROTATION_INTERVAL
        )

        if category == "custom_text":
            self._animate_custom_text(
                payload,
                total_duration,
                safe_slot,
                should_interrupt=should_interrupt,
            )
            return

        if category == "pokemon":
            self._animate_pokemon(
                payload,
                total_duration,
                safe_slot,
                should_interrupt=should_interrupt,
            )
            return

        if category == "joke":
            self._animate_joke(
                payload,
                total_duration,
                safe_slot,
                should_interrupt=should_interrupt,
            )
            return

        if category == "weather":
            self._animate_weather_ticker(
                payload,
                total_duration,
                safe_slot,
                should_interrupt=should_interrupt,
            )
            return

        image = self.render_payload(payload)
        if self._transition_to(
            image,
            preview_name=f"{safe_slot}_{category}.png",
            steps=5,
            delay=0.03,
            should_interrupt=should_interrupt,
        ):
            return

        if duration_seconds is not None:
            sleep_time = max(0, duration_seconds - 0.20)
            if sleep_time > 0:
                self._sleep_with_interrupt(sleep_time, should_interrupt)
