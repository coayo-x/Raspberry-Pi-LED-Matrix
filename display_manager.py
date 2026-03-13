import io
import time
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import adafruit_blinka_raspberry_pi5_piomatter as piomatter
except ImportError:
    piomatter = None


WIDTH = 64
HEIGHT = 32

PANEL_COLS = 1
PANEL_ROWS = 1
PANEL_ROTATIONS = ((0,),)


GLOBAL_ROTATE_180 = True

DEFAULT_BG = (0, 0, 0, 255)


TEXT_PRIMARY = (170, 170, 170, 255)
TEXT_SECONDARY = (120, 130, 135, 255)
TEXT_ACCENT = (105, 125, 145, 255)
ICON_MAIN = (135, 145, 155, 255)
ICON_ALT = (90, 110, 125, 255)


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
        self.use_matrix = use_matrix and piomatter is not None
        self.preview_dir = Path(preview_dir)
        self.preview_dir.mkdir(parents=True, exist_ok=True)
        self.save_previews = save_previews

        self.font = ImageFont.load_default()
        self.small_font = self._load_small_font()
        self.line_height = self._get_line_height(self.font)
        self.small_line_height = self._get_line_height(self.small_font)

        self.matrix = None
        self.framebuffer = None
        self.last_frame: Optional[Image.Image] = None

        if self.use_matrix:
            geometry = piomatter.Geometry(
                width=self.width,
                height=self.height,
                n_addr_lines=4,
            )
            pinout = piomatter.Pinout.AdafruitMatrixHatBGR
            colorspace = piomatter.Colorspace.RGB888
            self.framebuffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            self.matrix = piomatter.PioMatter(colorspace, pinout, self.framebuffer, geometry)

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

    def _prepare_image(self, image: Image.Image) -> Image.Image:
        img = image.convert("RGBA").resize((self.width, self.height), Image.NEAREST)

        if PANEL_COLS == 1 and PANEL_ROWS == 1:
            angle = PANEL_ROTATIONS[0][0]
            if angle:
                img = img.rotate(angle, expand=False)

        if GLOBAL_ROTATE_180:
            img = img.rotate(180, expand=False)

        return img

    def _push_prepared(self, image: Image.Image) -> None:
        if self.use_matrix and self.matrix is not None and self.framebuffer is not None:
            arr = np.array(image, dtype=np.uint8)
            self.framebuffer[:] = np.flipud(np.fliplr(arr))
            self.matrix.show()

    def _save_prepared(self, image: Image.Image, preview_name: Optional[str]) -> None:
        if self.save_previews and preview_name:
            image.save(self.preview_dir / preview_name)

    def _transition_to(
        self,
        target_image: Image.Image,
        preview_name: Optional[str] = None,
        steps: int = 6,
        delay: float = 0.035,
    ) -> None:
        target = self._prepare_image(target_image)

        if self.last_frame is None:
            for i in range(1, steps + 1):
                cut = int(self.width * i / steps)
                frame = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
                frame.paste(target.crop((0, 0, cut, self.height)), (0, 0))
                self._push_prepared(frame)
                time.sleep(delay)
        else:
            for i in range(1, steps + 1):
                alpha = i / steps
                frame = Image.blend(self.last_frame, target, alpha)
                self._push_prepared(frame)
                time.sleep(delay)

        self._push_prepared(target)
        self._save_prepared(target, preview_name)
        self.last_frame = target

    def _show_frame(self, image: Image.Image, preview_name: Optional[str] = None) -> None:
        prepared = self._prepare_image(image)
        self._push_prepared(prepared)
        self._save_prepared(prepared, preview_name)
        self.last_frame = prepared

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

    def _fit_image(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        working = image.copy().convert("RGBA")
        working.thumbnail((target_width, target_height), Image.LANCZOS)
        canvas = Image.new("RGBA", (target_width, target_height), DEFAULT_BG)
        x = (target_width - working.width) // 2
        y = (target_height - working.height) // 2
        canvas.paste(working, (x, y), working)
        return canvas

    def _draw_line(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill=TEXT_PRIMARY) -> None:
        draw.text((x, y), text, font=self.font, fill=fill)

    def _get_line_height(self, font) -> int:
        bbox = font.getbbox("Ag")
        return max(7, bbox[3] - bbox[1] + 1)

    def _text_width(self, text: str, font=None) -> int:
        active_font = font or self.font
        return active_font.getbbox(text)[2]

    def _truncate_to_width(self, text: str, max_width_px: int, font=None) -> str:
        if not text:
            return ""

        active_font = font or self.font
        value = str(text)
        while value and active_font.getbbox(value)[2] > max_width_px:
            value = value[:-1]
        return value

    def _wrap_text(self, text: str, width_px: int, font=None) -> list[str]:
        active_font = font or self.font
    def _wrap_text(self, text: str, width_px: int) -> list[str]:
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return [""]

        wrapped: list[str] = []
        words = cleaned.split(" ")
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and active_font.getbbox(candidate)[2] > width_px:
            if line and self.font.getbbox(candidate)[2] > width_px:
                wrapped.append(line)
                line = word
            else:
                line = candidate

            while active_font.getbbox(line)[2] > width_px:
            while self.font.getbbox(line)[2] > width_px:
                wrapped.append(line[:-1])
                line = line[-1]

        wrapped.append(line)
        return wrapped or [""]

    def _draw_text_centered(
        self,
        draw: ImageDraw.ImageDraw,
        lines: list[str],
        fill=TEXT_PRIMARY,
        font=None,
        line_height: Optional[int] = None,
    ) -> None:
        active_font = font or self.font
        active_line_height = line_height if line_height is not None else self._get_line_height(active_font)
        total_height = len(lines) * active_line_height
    def _draw_text_centered(self, draw: ImageDraw.ImageDraw, lines: list[str], fill=TEXT_PRIMARY) -> None:
        total_height = len(lines) * self.line_height
        y = max(0, (self.height - total_height) // 2)

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=active_font)
            text_width = bbox[2] - bbox[0]
            x = max(0, (self.width - text_width) // 2)
            draw.text((x, y), line, font=active_font, fill=fill)
            y += active_line_height
            draw.text((x, y), line, font=self.font, fill=fill)
            y += self.line_height

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

    def _draw_weather_icon(self, draw: ImageDraw.ImageDraw, condition: str, x: int, y: int) -> None:
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
        title_lines = self._wrap_text("Today's Pokémon is:", self.width - 4)
        name = self._truncate_to_width(str(data.get("name", "Unknown")), self.width - 4)
        self._draw_text_centered(draw, title_lines + [name], fill=TEXT_PRIMARY)
        return img

    def _render_pokemon_base(self, data: dict) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        art_box_w = 24
        art_box_h = 24
        art_x = self.width - art_box_w - 1
        art_y = 4
        text_max_width = art_x - 2

        name = self._truncate_to_width(str(data.get("name", "Unknown")), text_max_width, font=self.small_font)
        self._draw_line(draw, 1, 1, name, fill=TEXT_ACCENT, font=self.small_font)
        header = self._truncate_to_width("Pokemon:", 26)
        name = self._truncate_to_width(str(data.get("name", "Unknown")), 26)
        self._draw_line(draw, 1, 1, header, fill=TEXT_SECONDARY)
        self._draw_line(draw, 1, 1 + self.line_height, name, fill=TEXT_ACCENT)

        art_box_w = 28
        art_box_h = 28
        art_x = self.width - art_box_w - 1
        art_y = 2

        art = None
        try:
            art = self._download_image(data.get("image_url"))
        except Exception:
            art = None

        if art is not None:
            art = self._fit_image(art, art_box_w, art_box_h)
            img.paste(art, (art_x, art_y), art)
        else:
            self._draw_line(draw, art_x + 1, art_y + 9, "NO IMG", fill=TEXT_SECONDARY, font=self.small_font)

        return img

    def _render_pokemon_info_frame(self, base: Image.Image, info_text: str, alpha: float = 1.0) -> Image.Image:
        img = base.copy()
        draw = ImageDraw.Draw(img)

        info_x = 1
        info_y = self.small_line_height + 3
        info_w = (self.width - 24 - 1) - 2

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
            self._draw_line(draw, art_x + 3, art_y + 10, "NO IMG", fill=TEXT_SECONDARY)

        return img

    def _render_pokemon_stat_overlay(self, base: Image.Image, line: str) -> Image.Image:
        img = base.copy()
        draw = ImageDraw.Draw(img)
        text = self._truncate_to_width(line, 30)
        self._draw_line(draw, 1, self.height - self.line_height - 1, text, fill=TEXT_PRIMARY)
        return img

    def render_weather(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        condition = str(data.get("condition", "Unknown"))
        self._draw_weather_icon(draw, condition, 1, 5)

        label = "Weather"
        label_width = self._text_width(label, font=self.small_font)
        label_x = max(24, min(self.width - label_width, (self.width - label_width) // 2))
        self._draw_line(draw, label_x, 2, label, fill=TEXT_ACCENT, font=self.small_font)
        draw.line((0, 13, self.width - 1, 13), fill=TEXT_SECONDARY)
        self._draw_weather_icon(draw, condition, 2, 5)
        self._draw_line(draw, 28, 11, "Weather", fill=TEXT_ACCENT)
        return img

    def _render_text_page(self, lines: list[str], fill=TEXT_PRIMARY) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_text_centered(draw, lines, fill=fill)
        return img

    def _paginate_lines(self, lines: list[str], max_lines: int = 3) -> list[list[str]]:
        pages = [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]
        return pages or [[""]]

    def _build_joke_pages(self, text: str, fill=TEXT_PRIMARY) -> list[Image.Image]:
        lines = self._wrap_text(text, width_px=self.width - 4)
        pages = self._paginate_lines(lines, max_lines=3)
        return [self._render_text_page(page, fill=fill) for page in pages]

    def render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]
        if data.get("type") == "twopart":
            setup_pages = self._build_joke_pages(data.get("setup") or "", fill=TEXT_PRIMARY)
            delivery_pages = self._build_joke_pages(data.get("delivery") or "", fill=TEXT_ACCENT)
            return setup_pages + delivery_pages
        return self._build_joke_pages(data.get("text") or "No joke", fill=TEXT_PRIMARY)

    def render_science(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        name = self._truncate_to_width(str(data.get("name", "Unknown")), self.width - 4)
        symbol = self._truncate_to_width(f"({data.get('symbol', '?')})", self.width - 4)
        atomic_number = data.get("atomic_number", "?")
        atomic_line = self._truncate_to_width(f"Atomic {atomic_number}", self.width - 4)

        lines = [name, symbol, atomic_line]
        self._draw_text_centered(draw, lines, fill=TEXT_PRIMARY)
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
        self._draw_line(draw, 2, 12, "UNKNOWN", fill=TEXT_PRIMARY)
        return img

    def _fade_sequence(self, image: Image.Image, steps: int = 6, fade_in: bool = True, delay: float = 0.05) -> None:
        if fade_in:
            factors = [i / steps for i in range(1, steps + 1)]
        else:
            factors = [i / steps for i in range(steps - 1, -1, -1)]
        for factor in factors:
            frame = Image.blend(self._new_canvas(), image, factor)
            self._show_frame(frame)
            time.sleep(delay)

    def _animate_pokemon(self, payload: dict, duration_seconds: int, safe_slot: str) -> None:
        data = payload["data"]
        end_time = time.time() + max(1, duration_seconds)

        intro = self._render_pokemon_center_title(data)
        intro_start = time.time()
        self._transition_to(intro, preview_name=f"{safe_slot}_pokemon_intro.png", steps=8, delay=0.04)
        elapsed = time.time() - intro_start
        if elapsed < 3.0:
            time.sleep(3.0 - elapsed)
        if time.time() >= end_time:
            return

        base = self._render_pokemon_base(data)
        self._transition_to(base, preview_name=f"{safe_slot}_pokemon_base.png", steps=8, delay=0.04)
        center = self._render_pokemon_center_title(data)
        self._fade_sequence(center, steps=8, fade_in=True, delay=0.05)
        if time.time() >= end_time:
            return

        compact = self._render_pokemon_base(data)
        self._transition_to(compact, preview_name=f"{safe_slot}_pokemon_base.png", steps=8, delay=0.04)

        stats = [
            f"Types: {'/'.join(data.get('types', [])) or 'Unknown'}",
            f"HP: {data.get('hp', '--')}",
            f"ATK: {data.get('attack', '--')}",
            f"DEF: {data.get('defense', '--')}",
            f"Height: {data.get('height', '--')}",
            f"Weight: {data.get('weight', '--')}",
        ]

        idx = 0
        while time.time() < end_time:
            text = stats[idx % len(stats)]

            for alpha in [0.2, 0.4, 0.6, 0.8, 1.0]:
                self._show_frame(self._render_pokemon_info_frame(base, text, alpha=alpha))
                time.sleep(0.05)

            hold_end = min(end_time, time.time() + 0.9)
            while time.time() < hold_end:
                self._show_frame(self._render_pokemon_info_frame(base, text, alpha=1.0))
                time.sleep(0.08)

            for alpha in [0.8, 0.6, 0.4, 0.2, 0.0]:
                self._show_frame(self._render_pokemon_info_frame(base, text, alpha=alpha))
                time.sleep(0.05)

            self._show_frame(base)
            idx += 1
        index = 0
        while time.time() < end_time:
            overlay = self._render_pokemon_stat_overlay(compact, stats[index % len(stats)])
            self._fade_sequence(overlay, steps=5, fade_in=True, delay=0.04)

            hold_end = min(end_time, time.time() + 0.9)
            while time.time() < hold_end:
                time.sleep(0.05)

            self._fade_sequence(overlay, steps=5, fade_in=False, delay=0.04)
            self._show_frame(compact)
            index += 1

    def _animate_joke(self, payload: dict, duration_seconds: int, safe_slot: str) -> None:
        data = payload["data"]
        end_time = time.time() + max(1, duration_seconds)

        segments: list[list[Image.Image]] = []
        if data.get("type") == "twopart":
            segments.append(self._build_joke_pages(data.get("setup") or "", fill=TEXT_PRIMARY))
            segments.append(self._build_joke_pages(data.get("delivery") or "", fill=TEXT_ACCENT))
        else:
            segments.append(self._build_joke_pages(data.get("text") or "No joke", fill=TEXT_PRIMARY))

        seg_idx = 0
        while time.time() < end_time:
            pages = segments[seg_idx % len(segments)]
            first = pages[0]
            self._transition_to(first, preview_name=f"{safe_slot}_joke_{seg_idx}_0.png", steps=6, delay=0.03)
            self._fade_sequence(first, steps=7, fade_in=True, delay=0.05)

            hold_end = min(end_time, time.time() + 10.0)
            page_idx = 0
            while time.time() < hold_end:
                page = pages[page_idx % len(pages)]
                self._show_frame(page, preview_name=f"{safe_slot}_joke_{seg_idx}_{page_idx}.png")
                self._transition_to(page, preview_name=f"{safe_slot}_joke_{seg_idx}_{page_idx}.png", steps=3, delay=0.03)
                page_duration = min(2.0, max(0.2, hold_end - time.time()))
                time.sleep(page_duration)
                page_idx += 1

            self._fade_sequence(pages[min(page_idx, len(pages) - 1)], steps=7, fade_in=False, delay=0.05)
            seg_idx += 1

    def _weather_ticker_frame(self, condition: str, ticker: str, x: int) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_weather_icon(draw, condition, 1, 5)

        label = "Weather"
        label_width = self._text_width(label, font=self.small_font)
        label_x = max(24, min(self.width - label_width, (self.width - label_width) // 2))
        self._draw_line(draw, label_x, 2, label, fill=TEXT_ACCENT, font=self.small_font)

        draw.line((0, 13, self.width - 1, 13), fill=TEXT_SECONDARY)
        self._draw_line(draw, x, 18, ticker, fill=TEXT_PRIMARY, font=self.small_font)
        return img

    def _animate_weather_ticker(self, payload: dict, duration_seconds: int, safe_slot: str) -> None:
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
        self._transition_to(first, preview_name=f"{safe_slot}_weather.png", steps=6, delay=0.03)

        while time.time() < end_time:
            x -= 1
            if x < -text_w:
                x = self.width
            frame = self._weather_ticker_frame(condition, ticker, x)
            self._show_frame(frame, preview_name=f"{safe_slot}_weather.png")
        text_w = self.font.getbbox(ticker)[2]
        x = self.width

        while time.time() < end_time:
            img = self._new_canvas()
            draw = ImageDraw.Draw(img)
            self._draw_weather_icon(draw, condition, 1, 5)
            self._draw_line(draw, 27, 2, "Weather", fill=TEXT_ACCENT)
            draw.line((0, 13, self.width - 1, 13), fill=TEXT_SECONDARY)
            self._draw_line(draw, x, 18, ticker, fill=TEXT_PRIMARY)
            self._show_frame(img, preview_name=f"{safe_slot}_weather.png")

            x -= 1
            if x < -text_w:
                x = self.width
            time.sleep(0.06)

    def display_payload(self, payload: dict, duration_seconds: Optional[int] = None) -> None:
        category = payload["category"]
        safe_slot = payload["slot_key"].replace(":", "-")
        total_duration = duration_seconds if duration_seconds is not None else 300

        if category == "pokemon":
            self._animate_pokemon(payload, total_duration, safe_slot)
            return

        if category == "joke":
            self._animate_joke(payload, total_duration, safe_slot)
            return

        if category == "weather":
            self._animate_weather_ticker(payload, total_duration, safe_slot)
            return

        image = self.render_payload(payload)
        self._transition_to(image, preview_name=f"{safe_slot}_{category}.png", steps=5, delay=0.03)

        if duration_seconds is not None:
            sleep_time = max(0, duration_seconds - 0.20)
            if sleep_time > 0:
                time.sleep(sleep_time)
