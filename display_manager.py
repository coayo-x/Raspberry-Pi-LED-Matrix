
import io
import math
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

PANEL_WIDTH = 64
PANEL_HEIGHT = 32
PANEL_COLS = 1
PANEL_ROWS = 2
WIDTH = PANEL_WIDTH * PANEL_COLS
HEIGHT = PANEL_HEIGHT * PANEL_ROWS

DEFAULT_BG = (6, 10, 18, 255)
CARD_BG = (12, 18, 30, 255)
CARD_ALT = (18, 26, 40, 255)
OUTLINE = (50, 72, 110, 255)
WHITE = (240, 244, 255, 255)
DIM = (164, 176, 204, 255)
YELLOW = (255, 213, 79, 255)
CYAN = (96, 220, 255, 255)
GREEN = (111, 238, 163, 255)
RED = (255, 120, 120, 255)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend([
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        ])
    candidates.extend([
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
    ])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


class DisplayManager:
    def __init__(
        self,
        width: int = WIDTH,
        height: int = HEIGHT,
        use_matrix: bool = True,
        preview_dir: str = 'preview_frames',
    ) -> None:
        self.width = width
        self.height = height
        self.use_matrix = use_matrix and piomatter is not None
        self.preview_dir = Path(preview_dir)
        self.preview_dir.mkdir(parents=True, exist_ok=True)

        self.font_sm = _load_font(8)
        self.font_md = _load_font(10, bold=True)
        self.font_lg = _load_font(15, bold=True)
        self.font_xl = _load_font(22, bold=True)

        self.matrix = None
        self.framebuffer = None
        self.last_frame: Optional[Image.Image] = None

        if self.use_matrix:
            addr_lines = 5 if height >= 64 else 4
            geometry = piomatter.Geometry(width=width, height=height, n_addr_lines=addr_lines)
            pinout = piomatter.Pinout.AdafruitMatrixHatBGR
            colorspace = piomatter.Colorspace.RGB888
            self.framebuffer = np.zeros((height, width, 4), dtype=np.uint8)
            self.matrix = piomatter.PioMatter(colorspace, pinout, self.framebuffer, geometry)

    def _text_size(self, text: str, font) -> tuple[int, int]:
        box = font.getbbox(text)
        return box[2] - box[0], box[3] - box[1]

    def _truncate(self, text: str, font, max_width: int) -> str:
        if self._text_size(text, font)[0] <= max_width:
            return text
        while text:
            trial = text[:-1].rstrip() + '…'
            if self._text_size(trial, font)[0] <= max_width:
                return trial
            text = text[:-1]
        return '…'

    def _wrap(self, text: str, font, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return ['']
        lines = []
        current = words[0]
        for word in words[1:]:
            trial = current + ' ' + word
            if self._text_size(trial, font)[0] <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _show_image(self, image: Image.Image, preview_name: Optional[str] = None) -> None:
        image = image.convert('RGBA').resize((self.width, self.height), Image.LANCZOS)
        if self.use_matrix and self.matrix is not None and self.framebuffer is not None:
            arr = np.array(image, dtype=np.uint8)
            self.framebuffer[:] = np.flipud(np.fliplr(arr))
            self.matrix.show()
        if preview_name:
            image.save(self.preview_dir / preview_name)
        self.last_frame = image.copy()

    def _download_image(self, url: Optional[str]) -> Optional[Image.Image]:
        if not url:
            return None
        req = urllib.request.Request(url, headers={'User-Agent': 'RaspberryPi-Pokemon-LED/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return Image.open(io.BytesIO(response.read())).convert('RGBA')

    def _card(self, img: Image.Image, xy: tuple[int, int, int, int], fill=CARD_BG) -> ImageDraw.ImageDraw:
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(xy, radius=6, fill=fill, outline=OUTLINE, width=1)
        return draw

    def _fit_image(self, image: Image.Image, target_width: int, target_height: int) -> Image.Image:
        working = image.copy().convert('RGBA')
        working.thumbnail((target_width, target_height), Image.LANCZOS)
        canvas = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        x = (target_width - working.width) // 2
        y = (target_height - working.height) // 2
        canvas.paste(working, (x, y), working)
        return canvas

    def _render_bg(self) -> Image.Image:
        img = Image.new('RGBA', (self.width, self.height), DEFAULT_BG)
        draw = ImageDraw.Draw(img)
        for y in range(self.height):
            factor = y / max(1, self.height - 1)
            color = (
                int(8 + 14 * factor),
                int(12 + 10 * factor),
                int(18 + 24 * factor),
                255,
            )
            draw.line((0, y, self.width, y), fill=color)
        return img

    def _draw_header(self, draw: ImageDraw.ImageDraw, title: str, subtitle: str = '') -> None:
        draw.rounded_rectangle((2, 2, self.width - 3, 15), radius=5, fill=(20, 30, 48, 255), outline=OUTLINE)
        draw.text((6, 4), title, font=self.font_md, fill=YELLOW)
        if subtitle:
            sub = self._truncate(subtitle, self.font_sm, self.width - 70)
            tw, _ = self._text_size(sub, self.font_sm)
            draw.text((self.width - tw - 6, 5), sub, font=self.font_sm, fill=DIM)

    def _draw_weather_icon(self, draw: ImageDraw.ImageDraw, x: int, y: int, condition: str) -> None:
        c = condition.lower()
        if 'thunder' in c:
            self._draw_cloud(draw, x, y, fill=(150, 170, 210, 255))
            draw.polygon([(x + 18, y + 18), (x + 28, y + 18), (x + 22, y + 30), (x + 30, y + 30), (x + 16, y + 46), (x + 20, y + 32), (x + 12, y + 32)], fill=YELLOW)
        elif 'snow' in c:
            self._draw_cloud(draw, x, y)
            for dx in (12, 22, 32):
                draw.line((x + dx - 3, y + 30, x + dx + 3, y + 36), fill=WHITE)
                draw.line((x + dx + 3, y + 30, x + dx - 3, y + 36), fill=WHITE)
        elif 'rain' in c or 'drizzle' in c or 'showers' in c:
            self._draw_cloud(draw, x, y)
            for dx in (12, 22, 32):
                draw.line((x + dx, y + 28, x + dx - 2, y + 38), fill=CYAN, width=2)
        elif 'fog' in c:
            self._draw_cloud(draw, x, y, fill=(180, 190, 205, 255))
            for iy in range(30, 42, 4):
                draw.line((x + 4, y + iy, x + 40, y + iy), fill=DIM)
        elif 'clear' in c:
            self._draw_sun(draw, x + 6, y + 4)
        elif 'cloud' in c:
            self._draw_cloud(draw, x, y)
        else:
            self._draw_sun(draw, x + 2, y + 2)
            self._draw_cloud(draw, x + 10, y + 10)

    def _draw_sun(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        draw.ellipse((x + 8, y + 8, x + 28, y + 28), fill=YELLOW)
        cx, cy = x + 18, y + 18
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1 = cx + math.cos(rad) * 14
            y1 = cy + math.sin(rad) * 14
            x2 = cx + math.cos(rad) * 21
            y2 = cy + math.sin(rad) * 21
            draw.line((x1, y1, x2, y2), fill=YELLOW, width=2)

    def _draw_cloud(self, draw: ImageDraw.ImageDraw, x: int, y: int, fill=(206, 216, 235, 255)) -> None:
        draw.ellipse((x + 4, y + 14, x + 22, y + 30), fill=fill)
        draw.ellipse((x + 16, y + 8, x + 34, y + 28), fill=fill)
        draw.ellipse((x + 28, y + 14, x + 44, y + 30), fill=fill)
        draw.rounded_rectangle((x + 8, y + 20, x + 40, y + 32), radius=6, fill=fill)

    def _transition_to(self, next_image: Image.Image, preview_prefix: Optional[str] = None, steps: int = 8, delay: float = 0.04) -> None:
        if self.last_frame is None:
            self._show_image(next_image, preview_name=f'{preview_prefix}_0.png' if preview_prefix else None)
            return

        prev = self.last_frame.copy().convert('RGBA')
        nxt = next_image.copy().convert('RGBA')
        for step in range(1, steps + 1):
            t = step / steps
            canvas = Image.new('RGBA', (self.width, self.height), DEFAULT_BG)

            prev_offset = int(-self.width * 0.18 * t)
            next_offset = int(self.width * (1 - t) * 0.18)

            prev_layer = prev.copy()
            prev_layer.putalpha(int(255 * (1 - t)))
            nxt_layer = nxt.copy()
            nxt_layer.putalpha(int(255 * t))

            canvas.alpha_composite(prev_layer, (prev_offset, 0))
            canvas.alpha_composite(nxt_layer, (next_offset, 0))

            self._show_image(canvas, preview_name=f'{preview_prefix}_transition_{step}.png' if preview_prefix and step == steps else None)
            time.sleep(delay)

    def render_pokemon(self, payload: dict) -> Image.Image:
        data = payload['data']
        img = self._render_bg()
        draw = ImageDraw.Draw(img)
        self._draw_header(draw, "TODAY'S POKEMON", payload['slot_key'])

        self._card(img, (4, 18, 34, 60), fill=(14, 22, 36, 255))
        art = None
        try:
            art = self._download_image(data.get('image_url'))
        except Exception:
            art = None
        if art is not None:
            art = self._fit_image(art, 28, 38)
            img.paste(art, (5, 20), art)
        else:
            draw.text((8, 34), 'NO', font=self.font_md, fill=RED)
            draw.text((8, 44), 'IMG', font=self.font_md, fill=RED)

        self._card(img, (36, 18, 60, 34), fill=CARD_BG)
        self._card(img, (36, 36, 60, 60), fill=CARD_ALT)
        name = self._truncate(data.get('name', 'Unknown'), self.font_md, 22)
        draw.text((39, 20), name, font=self.font_md, fill=YELLOW)
        types = '/'.join(data.get('types', [])) or 'Unknown'
        for idx, line in enumerate(self._wrap(types, self.font_sm, 20)[:2]):
            draw.text((39, 29 + idx * 8), line, font=self.font_sm, fill=CYAN)
        draw.text((39, 39), f'HP {data.get("hp", "--")}', font=self.font_sm, fill=GREEN)
        draw.text((39, 47), f'ATK {data.get("attack", "--")}', font=self.font_sm, fill=WHITE)
        draw.text((39, 55), f'DEF {data.get("defense", "--")}', font=self.font_sm, fill=DIM)
        return img

    def render_weather(self, payload: dict) -> Image.Image:
        data = payload['data']
        img = self._render_bg()
        draw = ImageDraw.Draw(img)
        self._draw_header(draw, 'WEATHER', data.get('location', ''))
        self._card(img, (4, 18, 28, 60), fill=(14, 22, 36, 255))
        self._draw_weather_icon(draw, 6, 22, str(data.get('condition', 'Unknown')))
        self._card(img, (30, 18, 60, 60), fill=CARD_BG)
        draw.text((34, 22), self._truncate(str(data.get('condition', 'Unknown')), self.font_md, 24), font=self.font_md, fill=YELLOW)
        temp = f'{data.get("temperature_f", "--")}°F'
        draw.text((34, 36), temp, font=self.font_lg, fill=WHITE)
        draw.text((34, 52), f'W {data.get("wind_mph", "--")} mph', font=self.font_sm, fill=CYAN)
        return img

    def render_temperature(self, payload: dict) -> Image.Image:
        data = payload['data']
        img = self._render_bg()
        draw = ImageDraw.Draw(img)
        self._draw_header(draw, 'TEMPERATURE', data.get('location', ''))
        self._card(img, (4, 18, 60, 60), fill=CARD_BG)
        temp = f'{data.get("temperature_f", "--")}°F'
        tw, _ = self._text_size(temp, self.font_xl)
        draw.text(((self.width - tw) // 2, 22), temp, font=self.font_xl, fill=WHITE)
        cond = self._truncate(str(data.get('condition', 'Unknown')), self.font_md, 54)
        cw, _ = self._text_size(cond, self.font_md)
        draw.text(((self.width - cw) // 2, 46), cond, font=self.font_md, fill=CYAN)
        return img

    def _render_joke_pages(self, payload: dict) -> list[Image.Image]:
        data = payload['data']
        if data.get('type') == 'single':
            lines = self._wrap(data.get('text') or 'No joke text', self.font_md, self.width - 10)
        else:
            setup = self._wrap(data.get('setup') or '', self.font_md, self.width - 10)
            delivery = self._wrap(data.get('delivery') or '', self.font_md, self.width - 10)
            lines = setup + [''] + delivery
        pages = [lines[i:i + 4] for i in range(0, len(lines), 4)] or [['No joke']]
        images = []
        for idx, page in enumerate(pages):
            img = self._render_bg()
            draw = ImageDraw.Draw(img)
            self._draw_header(draw, f'JOKE {idx + 1}/{len(pages)}', payload['slot_key'])
            self._card(img, (4, 18, 60, 60), fill=CARD_BG)
            y = 22
            for line in page:
                draw.text((8, y), self._truncate(line, self.font_md, self.width - 12), font=self.font_md, fill=WHITE if line else DIM)
                y += 9
            images.append(img)
        return images

    def render_payload_frames(self, payload: dict) -> list[Image.Image]:
        category = payload['category']
        if category == 'pokemon':
            return [self.render_pokemon(payload)]
        if category == 'weather':
            return [self.render_weather(payload)]
        if category == 'temperature':
            return [self.render_temperature(payload)]
        if category == 'joke':
            return self._render_joke_pages(payload)
        return [self._render_bg()]

    def display_payload(self, payload: dict, duration_seconds: Optional[int] = None) -> None:
        frames = self.render_payload_frames(payload)
        safe_slot = payload['slot_key'].replace(':', '-')
        if not frames:
            return

        self._transition_to(frames[0], preview_prefix=f'{safe_slot}_{payload["category"]}')

        if duration_seconds is None:
            return

        remaining = max(1.0, float(duration_seconds) - 0.35)

        if len(frames) == 1:
            self._show_image(frames[0], preview_name=f'{safe_slot}_{payload["category"]}.png')
            time.sleep(remaining)
            return

        page_duration = max(2.0, remaining / len(frames))
        start_idx = 0
        self._show_image(frames[start_idx], preview_name=f'{safe_slot}_{payload["category"]}_page0.png')
        time.sleep(min(page_duration, remaining))
        remaining -= min(page_duration, remaining)
        idx = 1
        while remaining > 0:
            frame = frames[idx % len(frames)]
            self._transition_to(frame)
            sleep_for = min(page_duration, remaining)
            time.sleep(sleep_for)
            remaining -= sleep_for
            idx += 1
