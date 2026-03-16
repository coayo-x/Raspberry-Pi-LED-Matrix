import atexit
import io
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageSequence
from config import ROTATION_INTERVAL

try:
    import adafruit_blinka_raspberry_pi5_piomatter as piomatter
except ImportError:
    piomatter = None


WIDTH = 64
HEIGHT = 32
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
        self.use_matrix = use_matrix and piomatter is not None
        self.save_previews = save_previews
        self.preview_dir = Path(preview_dir)
        self.assets_dir = Path(__file__).with_name("assets")
        self.alien_animation_path = self.assets_dir / "alien.gif"
        self.alien_audio_path = self.assets_dir / "Alien.mp3"
        if self.save_previews:
            self.preview_dir.mkdir(parents=True, exist_ok=True)

        self.font = ImageFont.load_default()
        self.small_font = self._load_small_font()
        self.line_height = self._get_line_height(self.font)
        self.small_line_height = self._get_line_height(self.small_font)

        self.matrix = None
        self.framebuffer = None
        self.last_frame: Optional[Image.Image] = None
        self._alien_frames: Optional[list[tuple[Image.Image, float]]] = None
        self._alien_audio_process: subprocess.Popen | None = None

        if self.use_matrix:
            geometry = piomatter.Geometry(
                width=self.width, height=self.height, n_addr_lines=4
            )
            pinout = piomatter.Pinout.AdafruitMatrixHatBGR
            colorspace = piomatter.Colorspace.RGB888
            self.framebuffer = np.zeros((self.height, self.width, 4), dtype=np.uint8)
            self.matrix = piomatter.PioMatter(
                colorspace, pinout, self.framebuffer, geometry
            )

        atexit.register(self._stop_alien_audio_loop)

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

    def _wrap_text(self, text: str, width_px: int, font=None) -> list[str]:
        active_font = font or self.font
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return [""]

        wrapped: list[str] = []
        words = cleaned.split(" ")
        line = ""

        for word in words:
            candidate = f"{line} {word}".strip()
            if line and self._text_width(candidate, active_font) > width_px:
                wrapped.append(line)
                line = word
            else:
                line = candidate

            while line and self._text_width(line, active_font) > width_px:
                wrapped.append(line[:-1])
                line = line[-1]

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
            arr = np.array(image, dtype=np.uint8)
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

    def _draw_alien_frame(self, phase: int) -> Image.Image:
        img = self._new_canvas()
        draw = ImageDraw.Draw(img)

        star_offsets = [0, 9, 18, 27, 36, 45, 54, 63]
        for offset in star_offsets:
            x = (offset + (phase * 3)) % self.width
            y = (7 + offset + (phase * 5)) % self.height
            draw.point((x, y), fill=(120, 180, 255, 255))

        floor_y = 26
        draw.line((0, floor_y, self.width - 1, floor_y), fill=(44, 84, 108, 255))

        body_x = 22 + (1 if phase % 2 == 0 else -1)
        body_y = 12 + (-1 if phase in {0, 3} else 0)
        accent = (164, 255, 138, 255)
        accent_soft = (118, 216, 248, 255)
        eye_fill = (8, 14, 18, 255)

        draw.polygon(
            [
                (body_x + 1, body_y + 2),
                (body_x + 5, body_y - 2),
                (body_x + 7, body_y + 4),
            ],
            fill=accent,
        )
        draw.polygon(
            [
                (body_x + 13, body_y + 2),
                (body_x + 9, body_y - 2),
                (body_x + 7, body_y + 4),
            ],
            fill=accent,
        )
        draw.ellipse((body_x, body_y, body_x + 14, body_y + 10), fill=accent)
        draw.ellipse((body_x + 3, body_y + 3, body_x + 6, body_y + 6), fill=eye_fill)
        draw.ellipse((body_x + 8, body_y + 3, body_x + 11, body_y + 6), fill=eye_fill)
        draw.arc(
            (body_x + 3, body_y + 5, body_x + 11, body_y + 9), 15, 165, fill=eye_fill
        )

        torso_x = body_x + 4
        torso_y = body_y + 9
        draw.rounded_rectangle(
            (torso_x, torso_y, torso_x + 7, torso_y + 8),
            radius=3,
            fill=accent_soft,
        )

        left_arm_y = torso_y + (phase % 3)
        right_arm_y = torso_y + 1 + ((phase + 1) % 3)
        draw.line(
            (torso_x, torso_y + 2, torso_x - 4, left_arm_y - 3),
            fill=accent_soft,
            width=2,
        )
        draw.line(
            (torso_x + 7, torso_y + 2, torso_x + 12, right_arm_y - 4),
            fill=accent_soft,
            width=2,
        )
        draw.line(
            (torso_x - 4, left_arm_y - 3, torso_x - 2, left_arm_y),
            fill=accent,
            width=2,
        )
        draw.line(
            (torso_x + 12, right_arm_y - 4, torso_x + 14, right_arm_y),
            fill=accent,
            width=2,
        )

        left_leg_shift = -2 if phase in {0, 2} else 1
        right_leg_shift = 2 if phase in {1, 3} else -1
        draw.line(
            (torso_x + 2, torso_y + 8, torso_x + left_leg_shift, floor_y - 1),
            fill=accent_soft,
            width=2,
        )
        draw.line(
            (torso_x + 5, torso_y + 8, torso_x + 7 + right_leg_shift, floor_y - 1),
            fill=accent_soft,
            width=2,
        )

        pet_x = 40 + (-1 if phase in {0, 3} else 1)
        pet_y = 14
        pet_fill = (255, 208, 110, 255)
        draw.ellipse((pet_x, pet_y, pet_x + 12, pet_y + 8), fill=pet_fill)
        draw.polygon(
            [(pet_x + 2, pet_y + 1), (pet_x + 4, pet_y - 3), (pet_x + 6, pet_y + 2)],
            fill=pet_fill,
        )
        draw.polygon(
            [(pet_x + 8, pet_y + 2), (pet_x + 10, pet_y - 2), (pet_x + 11, pet_y + 3)],
            fill=pet_fill,
        )
        draw.ellipse((pet_x + 8, pet_y + 2, pet_x + 10, pet_y + 4), fill=eye_fill)
        draw.line(
            (pet_x + 3, pet_y + 8, pet_x + 2, floor_y - 2), fill=pet_fill, width=2
        )
        draw.line(
            (pet_x + 8, pet_y + 8, pet_x + 9, floor_y - 1), fill=pet_fill, width=2
        )
        tail_shift = -3 if phase in {0, 2} else 3
        draw.arc(
            (
                pet_x + 9 + min(0, tail_shift),
                pet_y + 2,
                pet_x + 18 + max(0, tail_shift),
                pet_y + 11,
            ),
            280 if tail_shift > 0 else 160,
            80 if tail_shift > 0 else 340,
            fill=pet_fill,
            width=2,
        )

        banner = "ALIEN DANCE"
        banner_width = self._text_width(banner, font=self.small_font)
        banner_x = max(0, (self.width - banner_width) // 2)
        self._draw_line(draw, banner_x, 1, banner, fill=accent, font=self.small_font)
        return img

    def _build_alien_fallback_frames(self) -> list[tuple[Image.Image, float]]:
        return [(self._draw_alien_frame(phase), 0.12) for phase in range(4)]

    def _load_alien_frames(self) -> list[tuple[Image.Image, float]]:
        if self._alien_frames is not None:
            return self._alien_frames

        frames: list[tuple[Image.Image, float]] = []
        if self.alien_animation_path.exists():
            try:
                with Image.open(self.alien_animation_path) as animation:
                    for frame in ImageSequence.Iterator(animation):
                        duration_ms = (
                            frame.info.get("duration")
                            or animation.info.get("duration")
                            or 80
                        )
                        frames.append(
                            (
                                self._fit_image(
                                    frame.convert("RGBA"), self.width, self.height
                                ),
                                max(0.04, duration_ms / 1000.0),
                            )
                        )
            except Exception:
                frames = []

        self._alien_frames = frames or self._build_alien_fallback_frames()
        return self._alien_frames

    def _resolve_alien_audio_command(self) -> list[str] | None:
        if not self.alien_audio_path.exists():
            return None

        audio_file = str(self.alien_audio_path)
        candidates = [
            [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                "quiet",
                "-stream_loop",
                "-1",
                audio_file,
            ],
            ["mpg123", "--quiet", "--loop", "-1", audio_file],
            ["mpv", "--no-video", "--really-quiet", "--loop-file=inf", audio_file],
            ["cvlc", "--intf", "dummy", "--loop", audio_file],
        ]
        for command in candidates:
            if shutil.which(command[0]):
                return command
        return None

    def _ensure_alien_audio_loop(self) -> None:
        if (
            self._alien_audio_process is not None
            and self._alien_audio_process.poll() is None
        ):
            return

        command = self._resolve_alien_audio_command()
        if command is None:
            return

        try:
            self._alien_audio_process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            self._alien_audio_process = None

    def _stop_alien_audio_loop(self) -> None:
        process = self._alien_audio_process
        self._alien_audio_process = None
        if process is None:
            return

        if process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

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

    def run_alien_animation(
        self,
        should_interrupt: Optional[Callable[[], bool]] = None,
    ) -> None:
        frames = self._load_alien_frames()
        self._ensure_alien_audio_loop()

        try:
            first_frame, _ = frames[0]
            if self._transition_to(
                first_frame,
                preview_name="alien_mode.png",
                steps=6,
                delay=0.03,
                should_interrupt=should_interrupt,
            ):
                return

            frame_index = 0
            while True:
                if self._is_interrupted(should_interrupt):
                    return

                frame, delay = frames[frame_index % len(frames)]
                self._show_frame(frame, preview_name="alien_mode.png")
                frame_index += 1
                if self._sleep_with_interrupt(delay, should_interrupt):
                    return
        finally:
            self._stop_alien_audio_loop()

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
