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

WIDTH = PANEL_COLS * PANEL_CHAIN_LENGTH
HEIGHT = PANEL_ROWS
DEFAULT_BG = (0, 0, 0, 255)

TEXT_PRIMARY = (170, 170, 170, 255)
TEXT_SECONDARY = (120, 130, 135, 255)
TEXT_ACCENT = (105, 125, 145, 255)
ICON_MAIN = (135, 145, 155, 255)
ICON_ALT = (90, 110, 125, 255)

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

        self.font = ImageFont.load_default()
        self.small_font = self._load_small_font()
        self.line_height = self._get_line_height(self.font)
        self.small_line_height = self._get_line_height(self.small_font)

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

    def _load_small_font(self):
        candidates = [
            ("DejaVuSans.ttf", 8),
            ("DejaVuSansMono.ttf", 8),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 8),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 8),
        ]
        for name, size in candidates:
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

        selected_family = font_candidates.get(family_key) or font_candidates["sans"]
        for candidate in selected_family[(bold, italic)]:
            try:
                return ImageFont.truetype(candidate, size=size)
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

    def _parse_hex_color(
        self, value: str | None, fallback
    ) -> tuple[int, int, int, int]:
        normalized = str(value or "").strip().lstrip("#")
        if len(normalized) != 6:
            return fallback

        try:
            return (
                int(normalized[0:2], 16),
                int(normalized[2:4], 16),
                int(normalized[4:6], 16),
                255,
            )
        except ValueError:
            return fallback

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
        title_lines = self._wrap_text(
            "Today's Pokémon is:", self.width - 4, font=self.small_font
        )
        name = self._truncate_to_width(
            str(data.get("name", "Unknown")), self.width - 4, font=self.small_font
        )
        self._draw_text_centered(
            draw, title_lines + [name], fill=TEXT_PRIMARY, font=self.small_font
        )
        return img

    def _render_pokemon_base_canvas(self, data: dict) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        art_box_w = 24
        art_box_h = 24
        art_x = self.width - art_box_w - 1
        art_y = 4

        art = None
        try:
            art = self._download_image(data.get("image_url"))
        except Exception:
            art = None

        if art is not None:
            art = self._fit_image(art, art_box_w, art_box_h)
            img.paste(art, (art_x, art_y), art)
        else:
            self._draw_line(
                draw,
                art_x + 1,
                art_y + 9,
                "NO IMG",
                fill=TEXT_SECONDARY,
                font=self.small_font,
            )

        return img

    def _build_pokemon_name_frames(
        self, base: Image.Image, data: dict
    ) -> list[Image.Image]:
        img = base.copy()
        draw = ImageDraw.Draw(img)

        art_box_w = 24
        art_x = self.width - art_box_w - 1
        text_max_width = art_x - 3
        name = str(data.get("name", "Unknown"))

        frames = self.render_scrolling_text(
            draw,
            name,
            font=self.small_font,
            x=1,
            y=1,
            max_width=text_max_width,
            fill=TEXT_ACCENT,
            gap=12,
            pause_frames=10,
            step_px=1,
        )
        return frames or [img]

    def _render_pokemon_base(self, data: dict) -> Image.Image:
        return self._build_pokemon_name_frames(
            self._render_pokemon_base_canvas(data), data
        )[0]

    def _render_pokemon_info_frame(
        self, base: Image.Image, info_text: str, alpha: float = 1.0
    ) -> Image.Image:
        img = base.copy()
        draw = ImageDraw.Draw(img)

        art_box_w = 24
        info_x = 1
        info_y = self.small_line_height + 4
        info_w = (self.width - art_box_w - 2) - info_x

        lines = self._wrap_text(info_text, width_px=info_w, font=self.small_font)[:3]
        text_alpha = max(0, min(255, int(255 * alpha)))
        fill = (TEXT_PRIMARY[0], TEXT_PRIMARY[1], TEXT_PRIMARY[2], text_alpha)

        for index, line in enumerate(lines):
            self._draw_line(
                draw,
                info_x,
                info_y + (index * self.small_line_height),
                line,
                fill=fill,
                font=self.small_font,
            )

        return img

    def render_weather(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        condition = str(data.get("condition", "Unknown"))
        self._draw_weather_icon(draw, condition, 2, 5)

        label = "Weather"
        label_width = self._text_width(label, font=self.small_font)
        label_x = max(
            24, min(self.width - label_width - 1, (self.width - label_width) // 2)
        )
        self._draw_line(draw, label_x, 2, label, fill=TEXT_ACCENT, font=self.small_font)
        draw.line((0, 13, self.width - 1, 13), fill=TEXT_SECONDARY)
        return img

    def _render_text_page(self, lines: list[str], fill=TEXT_PRIMARY) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_text_centered(draw, lines, fill=fill, font=self.small_font)
        return img

    def _paginate_lines(self, lines: list[str], max_lines: int = 3) -> list[list[str]]:
        pages = [lines[i : i + max_lines] for i in range(0, len(lines), max_lines)]
        return pages or [[""]]

    def _build_joke_pages(self, text: str, fill=TEXT_PRIMARY) -> list[Image.Image]:
        lines = self._wrap_text(text, width_px=self.width - 4, font=self.small_font)
        pages = self._paginate_lines(lines, max_lines=3)
        return [self._render_text_page(page, fill=fill) for page in pages]

    def render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]
        if data.get("type") == "twopart":
            setup_pages = self._build_joke_pages(
                data.get("setup") or "", fill=TEXT_PRIMARY
            )
            delivery_pages = self._build_joke_pages(
                data.get("delivery") or "", fill=TEXT_ACCENT
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
        text_fill = self._parse_hex_color(style.get("text_color"), TEXT_PRIMARY)
        background_fill = self._parse_hex_color(
            style.get("background_color"), DEFAULT_BG
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
        end_time = time.time() + max(1, duration_seconds)

        intro = self._render_pokemon_center_title(data)
        intro_start = time.time()
        if self._transition_to(
            intro,
            preview_name=f"{safe_slot}_pokemon_intro.png",
            steps=8,
            delay=0.04,
            should_interrupt=should_interrupt,
        ):
            return True
        elapsed = time.time() - intro_start
        if elapsed < 3.0 and self._sleep_with_interrupt(
            3.0 - elapsed, should_interrupt
        ):
            return True
        if time.time() >= end_time or self._is_interrupted(should_interrupt):
            return self._is_interrupted(should_interrupt)

        base_canvas = self._render_pokemon_base_canvas(data)
        name_frames = self._build_pokemon_name_frames(base_canvas, data)
        name_frame_index = 0
        if self._transition_to(
            name_frames[0],
            preview_name=f"{safe_slot}_pokemon_base.png",
            steps=8,
            delay=0.04,
            should_interrupt=should_interrupt,
        ):
            return True

        stats = [
            f"Types: {'/'.join(data.get('types', [])) or 'Unknown'}",
            f"HP: {data.get('hp', '--')}",
            f"ATK: {data.get('attack', '--')}",
            f"DEF: {data.get('defense', '--')}",
            f"Height: {data.get('height', '--')}",
            f"Weight: {data.get('weight', '--')}",
        ]

        index = 0
        while time.time() < end_time:
            if self._is_interrupted(should_interrupt):
                return True

            text = stats[index % len(stats)]

            for alpha in [0.2, 0.4, 0.6, 0.8, 1.0]:
                current_base = name_frames[name_frame_index % len(name_frames)]
                self._show_frame(
                    self._render_pokemon_info_frame(current_base, text, alpha=alpha)
                )
                name_frame_index += 1
                if self._sleep_with_interrupt(0.05, should_interrupt):
                    return True

            hold_end = min(end_time, time.time() + 0.9)
            while time.time() < hold_end:
                current_base = name_frames[name_frame_index % len(name_frames)]
                self._show_frame(
                    self._render_pokemon_info_frame(current_base, text, alpha=1.0)
                )
                name_frame_index += 1
                if self._sleep_with_interrupt(0.08, should_interrupt):
                    return True

            for alpha in [0.8, 0.6, 0.4, 0.2, 0.0]:
                current_base = name_frames[name_frame_index % len(name_frames)]
                self._show_frame(
                    self._render_pokemon_info_frame(current_base, text, alpha=alpha)
                )
                name_frame_index += 1
                if self._sleep_with_interrupt(0.05, should_interrupt):
                    return True

            self._show_frame(name_frames[name_frame_index % len(name_frames)])
            name_frame_index += 1
            index += 1
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
                self._build_joke_pages(data.get("setup") or "", fill=TEXT_PRIMARY)
            )
            segments.append(
                self._build_joke_pages(data.get("delivery") or "", fill=TEXT_ACCENT)
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

    def _weather_ticker_frame(self, condition: str, ticker: str, x: int) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_weather_icon(draw, condition, 2, 5)

        label = "Weather"
        label_width = self._text_width(label, font=self.small_font)
        label_x = max(
            24, min(self.width - label_width - 1, (self.width - label_width) // 2)
        )
        self._draw_line(draw, label_x, 2, label, fill=TEXT_ACCENT, font=self.small_font)
        draw.line((0, 13, self.width - 1, 13), fill=TEXT_SECONDARY)
        self._draw_line(draw, x, 18, ticker, fill=TEXT_PRIMARY, font=self.small_font)
        return img

    def _animate_weather_ticker(
        self,
        payload: dict,
        duration_seconds: int,
        safe_slot: str,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> bool:
        data = payload["data"]
        condition = str(data.get("condition", "Unknown"))
        temp = str(data.get("temperature_f", "--"))
        wind = str(data.get("wind_mph", "--"))
        location = str(data.get("location", ""))
        ticker = f"{location} | {condition} | {temp}F | Wind {wind} mph   "

        end_time = time.time() + max(1, duration_seconds)
        text_w = self._text_width(ticker, font=self.small_font)
        x = self.width

        first = self._weather_ticker_frame(condition, ticker, x)
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

            frame = self._weather_ticker_frame(condition, ticker, x)
            self._show_frame(frame, preview_name=f"{safe_slot}_weather.png")
            x -= 1
            if x < -text_w:
                x = self.width
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
