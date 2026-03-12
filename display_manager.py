import io
import textwrap
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
DEFAULT_BG = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
DIM_WHITE = (180, 180, 180, 255)
YELLOW = (255, 220, 80, 255)
CYAN = (80, 220, 255, 255)
GREEN = (120, 255, 120, 255)


class DisplayManager:
    def __init__(
        self,
        width: int = WIDTH,
        height: int = HEIGHT,
        use_matrix: bool = True,
        preview_dir: str = "preview_frames",
    ) -> None:
        self.width = width
        self.height = height
        self.use_matrix = use_matrix and piomatter is not None
        self.preview_dir = Path(preview_dir)
        self.preview_dir.mkdir(parents=True, exist_ok=True)

        self.font = ImageFont.load_default()
        self.matrix = None
        self.framebuffer = None

        if self.use_matrix:
            geometry = piomatter.Geometry(width=width, height=height, n_addr_lines=4)
            pinout = piomatter.Pinout.AdafruitMatrixHatBGR
            colorspace = piomatter.Colorspace.RGB888
            self.framebuffer = np.zeros((height, width, 4), dtype=np.uint8)
            self.matrix = piomatter.PioMatter(colorspace, pinout, self.framebuffer, geometry)

    def _show_image(self, image: Image.Image, preview_name: Optional[str] = None) -> None:
        image = image.convert("RGBA").resize((self.width, self.height), Image.NEAREST)

        if self.use_matrix and self.matrix is not None and self.framebuffer is not None:
            arr = np.array(image, dtype=np.uint8)
            self.framebuffer[:] = np.flipud(np.fliplr(arr))
            self.matrix.show()

        if preview_name:
            image.save(self.preview_dir / preview_name)

    def _download_image(self, url: Optional[str]) -> Optional[Image.Image]:
        if not url:
            return None

        req = urllib.request.Request(url, headers={"User-Agent": "RaspberryPi-Pokemon-LED/1.0"})
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

    def _line(self, draw: ImageDraw.ImageDraw, x: int, y: int, text: str, fill=WHITE) -> None:
        draw.text((x, y), text[:18], font=self.font, fill=fill)

    def _wrap_text(self, text: str, width_chars: int = 14) -> list[str]:
        text = " ".join(text.split())
        if not text:
            return [""]
        return textwrap.wrap(text, width=width_chars, break_long_words=True, replace_whitespace=False)

    def _render_placeholder(self, title: str, message: str) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
        draw = ImageDraw.Draw(img)
        self._line(draw, 2, 2, title.upper(), fill=YELLOW)
        lines = self._wrap_text(message, width_chars=14)
        y = 12
        for line in lines[:3]:
            self._line(draw, 2, y, line, fill=WHITE)
            y += 8
        return img

    def render_pokemon(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
        draw = ImageDraw.Draw(img)

        art = None
        try:
            art = self._download_image(data.get("image_url"))
        except Exception:
            art = None

        if art is not None:
            art = self._fit_image(art, 32, 32)
            img.paste(art, (0, 0), art)
        else:
            placeholder = self._render_placeholder("pokemon", "image unavailable")
            crop = placeholder.crop((0, 0, 32, 32))
            img.paste(crop, (0, 0))

        draw.rectangle((32, 0, 63, 31), fill=(0, 0, 0, 255))
        self._line(draw, 34, 2, data.get("name", "Unknown"), fill=YELLOW)
        types = "/".join(data.get("types", [])) or "Unknown"
        self._line(draw, 34, 10, types, fill=CYAN)
        self._line(draw, 34, 18, f"HP {data.get('hp', '--')}", fill=GREEN)
        self._line(draw, 34, 26, f"A{data.get('attack', '--')} D{data.get('defense', '--')}", fill=WHITE)
        return img

    def render_weather(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
        draw = ImageDraw.Draw(img)
        self._line(draw, 2, 2, "WEATHER", fill=YELLOW)
        self._line(draw, 2, 10, str(data.get("condition", "Unknown")), fill=CYAN)
        self._line(draw, 2, 18, f"{data.get('temperature_f', '--')}F", fill=WHITE)
        self._line(draw, 2, 26, f"W {data.get('wind_mph', '--')}mph", fill=DIM_WHITE)
        return img

    def render_temperature(self, payload: dict) -> Image.Image:
        data = payload["data"]
        img = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
        draw = ImageDraw.Draw(img)
        self._line(draw, 2, 2, "TEMP", fill=YELLOW)
        temp = f"{data.get('temperature_f', '--')}F"
        self._line(draw, 2, 14, temp, fill=WHITE)
        self._line(draw, 2, 24, str(data.get("condition", "Unknown")), fill=CYAN)
        return img

    def _render_joke_page(self, page_lines: list[str], page_index: int, total_pages: int) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height), DEFAULT_BG)
        draw = ImageDraw.Draw(img)
        self._line(draw, 2, 2, f"JOKE {page_index + 1}/{total_pages}", fill=YELLOW)
        y = 10
        for line in page_lines[:3]:
            self._line(draw, 2, y, line, fill=WHITE)
            y += 8
        return img

    def render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload["data"]
        if data.get("type") == "single":
            full_text = data.get("text") or "No joke text"
        else:
            full_text = f"{data.get('setup', '')} ... {data.get('delivery', '')}".strip()

        lines = self._wrap_text(full_text, width_chars=14)
        pages = [lines[i:i + 3] for i in range(0, len(lines), 3)] or [["No joke"]]
        return [self._render_joke_page(page, idx, len(pages)) for idx, page in enumerate(pages)]

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
        return self._render_placeholder("error", f"Unknown category {category}")

    def display_payload(self, payload: dict, duration_seconds: Optional[int] = None) -> None:
        category = payload["category"]
        safe_slot = payload["slot_key"].replace(":", "-")

        if category == "joke":
            pages = self.render_joke_pages(payload)
            if duration_seconds is None:
                duration_seconds = 2

            end_time = time.time() + max(1, duration_seconds)
            page_index = 0

            while time.time() < end_time:
                page = pages[page_index % len(pages)]
                self._show_image(page, preview_name=f"{safe_slot}_{category}_{page_index % len(pages)}.png")
                page_index += 1
                time.sleep(min(2, max(0.2, end_time - time.time())))
            return

        image = self.render_payload(payload)
        self._show_image(image, preview_name=f"{safe_slot}_{category}.png")

        if duration_seconds is not None:
            time.sleep(max(0, duration_seconds))