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
        self.line_height = self._get_line_height()
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

    def _draw_line(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        fill=TEXT_PRIMARY,
    ) -> None:
        draw.text((x, y), text, font=self.font, fill=fill)

    def _get_line_height(self) -> int:
        bbox = self.font.getbbox("Ag")
        return max(8, bbox[3] - bbox[1] + 1)

    def _truncate_to_width(self, text: str, max_width_px: int) -> str:
        if not text:
            return ""

        value = str(text)
        while value and self.font.getbbox(value)[2] > max_width_px:
            value = value[:-1]
        return value

    def _wrap_text(self, text: str, width_px: int) -> list[str]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return [""]

        wrapped: list[str] = []
        for paragraph in cleaned.split("\n"):
            words = paragraph.split(" ")
            line = ""

            for word in words:
                candidate = f"{line} {word}".strip()
                if line and self.font.getbbox(candidate)[2] > width_px:
                    wrapped.append(line)
                    line = word
                else:
                    line = candidate

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
    ) -> None:
        total_height = len(lines) * self.line_height
        y = max(0, (self.height - total_height) // 2)

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=self.font)
            text_width = bbox[2] - bbox[0]
            x = max(0, (self.width - text_width) // 2)
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

    def render_pokemon(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        art_box_w = 26
        art_box_h = 26
        art_x = self.width - art_box_w - 2
        art_y = 3

        art = None
        try:
            art = self._download_image(data.get("image_url"))
        except Exception:
            art = None

        if art is not None:
            art = self._fit_image(art, art_box_w, art_box_h)
            img.paste(art, (art_x, art_y), art)
        else:
            self._draw_line(draw, art_x + 3, art_y + 10, "NO IMG", fill=TEXT_SECONDARY)

        text_max_width = art_x - 4
        name = self._truncate_to_width(str(data.get("name", "Unknown")), text_max_width)
        types = self._truncate_to_width("/".join(data.get("types", [])) or "Unknown", text_max_width)
        hp = data.get("hp", "--")
        atk = data.get("attack", "--")
        deff = data.get("defense", "--")
        stats = self._truncate_to_width(f"HP {hp} A{atk} D{deff}", text_max_width)

        self._draw_line(draw, 2, 2, name, fill=TEXT_ACCENT)
        self._draw_line(draw, 2, 2 + self.line_height, types, fill=TEXT_SECONDARY)
        self._draw_line(draw, 2, 2 + (2 * self.line_height), stats, fill=TEXT_PRIMARY)

        return img

    def render_weather(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        text_max_width = 38
        condition = self._truncate_to_width(str(data.get("condition", "Unknown")), text_max_width)
        temp = str(data.get("temperature_f", "--"))
        wind = str(data.get("wind_mph", "--"))
        temp_text = self._truncate_to_width(f"{temp}F", text_max_width)
        wind_text = self._truncate_to_width(f"W {wind}", text_max_width)

        self._draw_line(draw, 2, 2, condition, fill=TEXT_ACCENT)
        self._draw_line(draw, 2, 2 + self.line_height, temp_text, fill=TEXT_PRIMARY)
        self._draw_line(draw, 2, 2 + (2 * self.line_height), wind_text, fill=TEXT_SECONDARY)

        self._draw_weather_icon(draw, condition, 42, 5)

        return img

    def render_temperature(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        text_max_width = self.width - 4
        temp = str(data.get("temperature_f", "--"))
        condition = self._truncate_to_width(str(data.get("condition", "Unknown")), text_max_width)
        wind = str(data.get("wind_mph", "--"))
        temp_text = self._truncate_to_width(f"{temp}F", text_max_width)
        wind_text = self._truncate_to_width(f"W {wind}", text_max_width)

        self._draw_line(draw, 2, 2, temp_text, fill=TEXT_PRIMARY)
        self._draw_line(draw, 2, 2 + self.line_height, condition, fill=TEXT_ACCENT)
        self._draw_line(draw, 2, 2 + (2 * self.line_height), wind_text, fill=TEXT_SECONDARY)

        return img

    def _render_text_page(self, lines: list[str], fill=TEXT_PRIMARY) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_text_centered(draw, lines, fill=fill)
        return img

    def render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]

        if data.get("type") == "single":
            text = data.get("text") or "No joke"
            lines = self._wrap_text(text, width_px=self.width - 4)
            pages = [lines[i:i + 3] for i in range(0, len(lines), 3)] or [["No joke"]]
            return [self._render_text_page(page, fill=TEXT_PRIMARY) for page in pages]

        setup = data.get("setup") or ""
        delivery = data.get("delivery") or ""

        setup_lines = self._wrap_text(setup, width_px=self.width - 4)
        delivery_lines = self._wrap_text(delivery, width_px=self.width - 4)

        pages = []
        for chunk_start in range(0, len(setup_lines), 3):
            pages.append(self._render_text_page(setup_lines[chunk_start:chunk_start + 3], fill=TEXT_PRIMARY))

        for chunk_start in range(0, len(delivery_lines), 3):
            pages.append(self._render_text_page(delivery_lines[chunk_start:chunk_start + 3], fill=TEXT_ACCENT))

        return pages or [self._render_text_page(["No joke"], fill=TEXT_PRIMARY)]

    def render_payload(self, payload: dict) -> Image.Image:
        category = payload["category"]
        if category == "pokemon":
            return self.render_pokemon(payload)
        if category == "weather":
            return self.render_weather(payload)
        if category == "temperature":
            return self.render_temperature(payload)
        if category == "joke":
            return self.render_joke_pages(payload)[0]

        img = self._new_canvas()
        draw = ImageDraw.Draw(img)
        self._draw_line(draw, 2, 12, "UNKNOWN", fill=TEXT_PRIMARY)
        return img

    def display_payload(self, payload: dict, duration_seconds: Optional[int] = None) -> None:
        category = payload["category"]
        safe_slot = payload["slot_key"].replace(":", "-")

        if category == "joke":
            pages = self.render_joke_pages(payload)
            total_duration = duration_seconds if duration_seconds is not None else max(2, 2 * len(pages))
            end_time = time.time() + max(1, total_duration)

            page_index = 0
            while time.time() < end_time:
                page = pages[page_index % len(pages)]
                preview_name = f"{safe_slot}_{category}_{page_index % len(pages)}.png"
                self._transition_to(page, preview_name=preview_name, steps=4, delay=0.03)

                page_index += 1
                page_duration = min(2.0, max(0.2, end_time - time.time()))
                page_end = time.time() + page_duration

                while time.time() < page_end:
                    time.sleep(0.08)

            return

        image = self.render_payload(payload)
        self._transition_to(image, preview_name=f"{safe_slot}_{category}.png", steps=5, delay=0.03)

        if duration_seconds is not None:
            sleep_time = max(0, duration_seconds - 0.20)
            if sleep_time > 0:
                time.sleep(sleep_time)
