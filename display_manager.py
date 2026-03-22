import io
import time
import urllib.request
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
JOKE_LABEL = TEXT_HIGHLIGHT
JOKE_DELIVERY = (135, 230, 202, 255)
POKEMON_NAME = (255, 224, 134, 255)
POKEMON_DETAIL = (201, 219, 236, 255)
POKEMON_STAT_LABEL = (120, 182, 219, 255)
POKEMON_ART_FRAME = (72, 121, 161, 255)
ICON_MAIN = (110, 178, 226, 255)
ICON_ALT = (255, 209, 118, 255)

PANEL_PADDING = 4
WEATHER_HEADER_HEIGHT = 18
WEATHER_TICKER_Y = 21

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
        self.line_height = self._get_line_height(self.font)
        self.small_line_height = self._get_line_height(self.small_font)
        self.medium_line_height = self._get_line_height(self.medium_font)
        self.large_line_height = self._get_line_height(self.large_font)
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
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
            ]
        else:
            names = [
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
                "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
            ]
            paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            ]

        for name in names + paths:
            try:
                return ImageFont.truetype(name, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

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

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        img = image.convert("RGBA").resize((self.width, self.height), Image.NEAREST)
        if GLOBAL_ROTATE_180:
            img = img.rotate(180, expand=False)
        return img

    def _push_prepared(self, image: Image.Image) -> None:
        if self.use_matrix and self.matrix is not None and self.framebuffer is not None:
            channel_count = self.framebuffer.shape[2]
            mode = "RGB" if channel_count == 3 else "RGBA"
            arr = np.array(image.convert(mode), dtype=np.uint8)
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
        self, image: Image.Image, target_width: int, target_height: int
    ) -> Image.Image:
        working = image.copy().convert("RGBA")
        working.thumbnail((target_width, target_height), Image.LANCZOS)
        canvas = Image.new("RGBA", (target_width, target_height), DEFAULT_BG)
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
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        title = "Today's Pokemon is"
        title_width = self._text_width(title, self.medium_font)
        title_x = max(2, (self.width - title_width) // 2)
        title_y = max(2, (self.height // 2) - self.large_line_height)
        self._draw_line(
            draw,
            title_x,
            title_y,
            title,
            fill=TEXT_ACCENT,
            font=self.medium_font,
        )

        name_lines, name_font = self._fit_pokemon_name_lines(
            str(data.get("name", "Unknown")),
            self.width - 12,
        )
        name_y = title_y + self.medium_line_height + 3
        name_line_height = self._get_line_height(name_font)
        for line in name_lines:
            line_width = self._text_width(line, name_font)
            line_x = max(2, (self.width - line_width) // 2)
            self._draw_line(draw, line_x, name_y, line, fill=POKEMON_NAME, font=name_font)
            name_y += name_line_height
        return img

    def _pokemon_artwork(self, data: dict) -> Optional[Image.Image]:
        art = None
        try:
            art = self._download_image(data.get("image_url"))
        except Exception:
            art = None
        return art

    def _fit_pokemon_name_lines(self, name: str, max_width_px: int):
        lines = self._wrap_text(name, max_width_px, font=self.medium_font)
        if len(lines) <= 2:
            return lines, self.medium_font

        lines = self._wrap_text(name, max_width_px, font=self.font)
        if len(lines) <= 2:
            return lines, self.font

        return [self._truncate_to_width(name, max_width_px, font=self.font)], self.font

    def _render_pokemon_showcase(self, data: dict) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_panel_backgrounds(draw)

        left_x0, left_x1 = self._panel_bounds(0)
        middle_x0, middle_x1 = self._panel_bounds(1)
        right_x0, right_x1 = self._panel_bounds(2)

        left_width = left_x1 - left_x0 + 1
        middle_width = middle_x1 - middle_x0 + 1
        right_width = right_x1 - right_x0 + 1

        title_lines = self._wrap_text(
            "Today's Pokemon is:",
            left_width - (PANEL_PADDING * 2),
            font=self.small_font,
        )
        name_lines, name_font = self._fit_pokemon_name_lines(
            str(data.get("name", "Unknown")),
            left_width - (PANEL_PADDING * 2),
        )
        name_line_height = self._get_line_height(name_font)
        title_block_height = len(title_lines) * self.small_line_height
        name_block_height = len(name_lines) * name_line_height
        content_y = max(
            2,
            (self.height - (title_block_height + name_block_height + 2)) // 2,
        )
        for line in title_lines:
            line_width = self._text_width(line, self.small_font)
            line_x = left_x0 + max(PANEL_PADDING, (left_width - line_width) // 2)
            self._draw_line(
                draw,
                line_x,
                content_y,
                line,
                fill=TEXT_ACCENT,
                font=self.small_font,
            )
            content_y += self.small_line_height

        content_y += 2
        for line in name_lines:
            line_width = self._text_width(line, name_font)
            line_x = left_x0 + max(PANEL_PADDING, (left_width - line_width) // 2)
            self._draw_line(
                draw,
                line_x,
                content_y,
                line,
                fill=POKEMON_NAME,
                font=name_font,
            )
            content_y += name_line_height

        types_text = "/".join(
            str(value) for value in data.get("types", []) if value
        ) or "Unknown"
        types_line = self._truncate_to_width(
            types_text,
            middle_width - (PANEL_PADDING * 2),
            font=self.small_font,
        )
        self._draw_line(
            draw,
            middle_x0 + PANEL_PADDING,
            4,
            types_line,
            fill=POKEMON_DETAIL,
            font=self.small_font,
        )
        self._draw_text_segments(
            draw,
            middle_x0 + PANEL_PADDING,
            12,
            [
                ("HP ", POKEMON_STAT_LABEL),
                (str(data.get("hp", "--")), TEXT_PRIMARY),
                ("  ATK ", POKEMON_STAT_LABEL),
                (str(data.get("attack", "--")), TEXT_PRIMARY),
            ],
            font=self.small_font,
        )
        self._draw_text_segments(
            draw,
            middle_x0 + PANEL_PADDING,
            20,
            [
                ("DEF ", POKEMON_STAT_LABEL),
                (str(data.get("defense", "--")), TEXT_PRIMARY),
            ],
            font=self.small_font,
        )
        self._draw_text_segments(
            draw,
            middle_x0 + PANEL_PADDING,
            27,
            [
                ("HT ", POKEMON_STAT_LABEL),
                (str(data.get("height", "--")), TEXT_PRIMARY),
                ("  WT ", POKEMON_STAT_LABEL),
                (str(data.get("weight", "--")), TEXT_PRIMARY),
            ],
            font=self.small_font,
        )

        art_frame = (right_x0 + 3, 2, right_x1 - 3, self.height - 3)
        draw.rectangle(art_frame, outline=POKEMON_ART_FRAME)
        art = self._pokemon_artwork(data)
        if art is not None:
            art = self._fit_image(art, right_width - 8, self.height - 8)
            art_x = right_x0 + ((right_width - art.width) // 2)
            art_y = (self.height - art.height) // 2
            img.paste(art, (art_x, art_y), art)
        else:
            no_img = "NO IMG"
            no_img_width = self._text_width(no_img, self.small_font)
            self._draw_line(
                draw,
                right_x0 + max(PANEL_PADDING, (right_width - no_img_width) // 2),
                (self.height - self.small_line_height) // 2,
                no_img,
                fill=TEXT_SECONDARY,
                font=self.small_font,
            )

        return img

    def _render_pokemon_base(self, data: dict) -> Image.Image:
        return self._render_pokemon_showcase(data)

    def render_weather(self, payload: dict) -> Image.Image:
        ticker = self._build_weather_ticker(payload["data"])
        return self._weather_ticker_frame(payload["data"], ticker, offset_px=0)

    def _render_joke_page(
        self,
        label: str,
        lines: list[str],
        *,
        fill=TEXT_PRIMARY,
        label_fill=JOKE_LABEL,
    ) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        label_x = 6
        label_y = 2
        self._draw_line(draw, label_x, label_y, label, fill=label_fill, font=self.small_font)
        label_width = self._text_width(label, self.small_font)
        draw.line(
            (label_x + label_width + 5, label_y + 4, self.width - 6, label_y + 4),
            fill=PANEL_DIVIDER,
        )

        top_y = 11
        total_height = len(lines) * self.medium_line_height
        body_y = max(top_y, top_y + max(0, (self.height - top_y - total_height) // 2))
        for line in lines:
            self._draw_line(draw, 6, body_y, line, fill=fill, font=self.medium_font)
            body_y += self.medium_line_height
        return img

    def _paginate_lines(self, lines: list[str], max_lines: int = 3) -> list[list[str]]:
        pages = [lines[i : i + max_lines] for i in range(0, len(lines), max_lines)]
        return pages or [[""]]

    def _build_joke_pages(self, text: str, fill=TEXT_PRIMARY) -> list[Image.Image]:
        lines = self._wrap_text(text, width_px=self.width - 12, font=self.medium_font)
        pages = self._paginate_lines(lines, max_lines=2)
        return [self._render_joke_page("JOKE", page, fill=fill) for page in pages]

    def render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]
        if data.get("type") == "twopart":
            setup_lines = self._wrap_text(
                data.get("setup") or "",
                width_px=self.width - 12,
                font=self.medium_font,
            )
            delivery_lines = self._wrap_text(
                data.get("delivery") or "",
                width_px=self.width - 12,
                font=self.medium_font,
            )
            setup_pages = [
                self._render_joke_page("SETUP", page, fill=TEXT_PRIMARY)
                for page in self._paginate_lines(setup_lines, max_lines=2)
            ]
            delivery_pages = [
                self._render_joke_page(
                    "PUNCHLINE",
                    page,
                    fill=JOKE_DELIVERY,
                    label_fill=JOKE_DELIVERY,
                )
                for page in self._paginate_lines(delivery_lines, max_lines=2)
            ]
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
    ) -> bool:
        factors = (
            [i / steps for i in range(1, steps + 1)]
            if fade_in
            else [i / steps for i in range(steps - 1, -1, -1)]
        )
        for factor in factors:
            frame = Image.blend(self._new_canvas(), image, factor)
            self._show_frame(frame)
            if self._sleep_with_interrupt(delay, should_interrupt):
                return True
        return False

    def _animate_pokemon(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        data = payload["data"]
        end_time = time.time() + max(1, duration_seconds)

        intro = self._render_pokemon_center_title(data)
        if self._transition_to(
            intro,
            preview_name=f"{safe_slot}_pokemon_intro.png",
            steps=8,
            delay=0.04,
            should_interrupt=should_interrupt,
        ):
            return True
        intro_hold = min(2.5, max(0.0, end_time - time.time() - 0.3))
        if intro_hold > 0 and self._sleep_with_interrupt(intro_hold, should_interrupt):
            return True
        if time.time() >= end_time or self._is_interrupted(should_interrupt):
            return self._is_interrupted(should_interrupt)

        showcase = self._render_pokemon_showcase(data)
        if self._transition_to(
            showcase,
            preview_name=f"{safe_slot}_pokemon_showcase.png",
            steps=8,
            delay=0.04,
            should_interrupt=should_interrupt,
        ):
            return True

        self._show_frame(showcase, preview_name=f"{safe_slot}_pokemon_showcase.png")
        remaining = max(0.0, end_time - time.time())
        return self._sleep_with_interrupt(remaining, should_interrupt)

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
            setup_lines = self._wrap_text(
                data.get("setup") or "",
                width_px=self.width - 12,
                font=self.medium_font,
            )
            delivery_lines = self._wrap_text(
                data.get("delivery") or "",
                width_px=self.width - 12,
                font=self.medium_font,
            )
            segments.append(
                [
                    self._render_joke_page("SETUP", page, fill=TEXT_PRIMARY)
                    for page in self._paginate_lines(setup_lines, max_lines=2)
                ]
            )
            segments.append(
                [
                    self._render_joke_page(
                        "PUNCHLINE",
                        page,
                        fill=JOKE_DELIVERY,
                        label_fill=JOKE_DELIVERY,
                    )
                    for page in self._paginate_lines(delivery_lines, max_lines=2)
                ]
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

    def _draw_weather_header(self, draw: ImageDraw.ImageDraw, data: dict) -> None:
        condition = str(data.get("condition", "Unknown"))
        location = self._truncate_to_width(
            str(data.get("location", "Unknown")),
            self.panel_width - 32,
            font=self.small_font,
        )
        temp_text = self._truncate_to_width(
            f"{data.get('temperature_f', '--')}F",
            self.panel_width - (PANEL_PADDING * 2),
            font=self.large_font,
        )
        wind_text = self._truncate_to_width(
            f"Wind {data.get('wind_mph', '--')} mph",
            self.panel_width - (PANEL_PADDING * 2),
            font=self.small_font,
        )

        condition_lines = self._wrap_text(
            condition.upper(),
            self.panel_width - (PANEL_PADDING * 2),
            font=self.medium_font,
        )
        condition_font = self.medium_font
        if len(condition_lines) > 1:
            condition_lines = self._wrap_text(
                condition,
                self.panel_width - (PANEL_PADDING * 2),
                font=self.small_font,
            )[:2]
            condition_font = self.small_font

        self._draw_panel_backgrounds(draw, top=0, bottom=WEATHER_HEADER_HEIGHT - 1)
        draw.line(
            (0, WEATHER_HEADER_HEIGHT, self.width - 1, WEATHER_HEADER_HEIGHT),
            fill=PANEL_DIVIDER,
        )

        self._draw_weather_icon(draw, condition, 5, 2)
        self._draw_line(draw, 29, 2, "WEATHER", fill=TEXT_ACCENT, font=self.small_font)
        self._draw_line(draw, 29, 10, location, fill=TEXT_SECONDARY, font=self.small_font)

        middle_x0, _ = self._panel_bounds(1)
        condition_y = (
            4
            if len(condition_lines) == 1
            else max(
                1,
                (
                    WEATHER_HEADER_HEIGHT
                    - (len(condition_lines) * self._get_line_height(condition_font))
                )
                // 2,
            )
        )
        for line in condition_lines:
            line_width = self._text_width(line, condition_font)
            line_x = middle_x0 + max(PANEL_PADDING, (self.panel_width - line_width) // 2)
            self._draw_line(
                draw,
                line_x,
                condition_y,
                line,
                fill=TEXT_PRIMARY,
                font=condition_font,
            )
            condition_y += self._get_line_height(condition_font)

        right_x0, _ = self._panel_bounds(2)
        temp_width = self._text_width(temp_text, self.large_font)
        self._draw_line(
            draw,
            right_x0 + max(PANEL_PADDING, (self.panel_width - temp_width) // 2),
            1,
            temp_text,
            fill=self._weather_temperature_fill(data.get("temperature_f")),
            font=self.large_font,
        )
        wind_width = self._text_width(wind_text, self.small_font)
        self._draw_line(
            draw,
            right_x0 + max(PANEL_PADDING, (self.panel_width - wind_width) // 2),
            11,
            wind_text,
            fill=TEXT_SECONDARY,
            font=self.small_font,
        )

    def _weather_ticker_frame(self, data: dict, ticker: str, offset_px: int) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_weather_header(draw, data)
        self._draw_repeating_ticker(
            draw,
            ticker,
            y=WEATHER_TICKER_Y,
            offset_px=offset_px,
            font=self.font,
            fill=WEATHER_TICKER,
        )
        return img

    def _animate_weather_ticker(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        data = payload["data"]
        ticker = self._build_weather_ticker(data)

        end_time = time.time() + max(1, duration_seconds)
        loop_width = max(1, self._text_width(ticker, font=self.font))
        offset_px = 0

        first = self._weather_ticker_frame(data, ticker, offset_px)
        if self._transition_to(
            first,
            preview_name=f"{safe_slot}_weather.png",
            steps=6,
            delay=0.03,
            should_interrupt=should_interrupt,
        ):
            return True

        while time.time() < end_time:
            if self._is_interrupted(should_interrupt):
                return True

            frame = self._weather_ticker_frame(data, ticker, offset_px)
            self._show_frame(frame, preview_name=f"{safe_slot}_weather.png")
            offset_px = (offset_px + 1) % loop_width
            if self._sleep_with_interrupt(0.06, should_interrupt):
                return True
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
