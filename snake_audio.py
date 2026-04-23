import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

try:
    import pygame
except ImportError:
    pygame = None


SOUND_FILENAMES = {
    "food": "music_food.mp3",
    "game_over": "music_gameover.mp3",
    "move": "music_move.mp3",
}
COMMAND_BACKENDS = (
    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"],
    ["mpg123", "-q"],
    ["mpg321", "-q"],
    ["mpv", "--no-video", "--really-quiet"],
    ["cvlc", "--play-and-exit", "--quiet"],
)
MIN_INTERVAL_SECONDS = {
    "move": 0.045,
    "food": 0.0,
    "game_over": 0.2,
}


class _NullAudioBackend:
    def play(self, sound_name: str) -> None:
        return

    def close(self) -> None:
        return


class _PygameAudioBackend:
    def __init__(self, sound_paths: dict[str, Path]) -> None:
        if pygame is None:
            raise RuntimeError("pygame is not installed")

        try:
            pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=256)
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self._sounds = {
                sound_name: pygame.mixer.Sound(str(path))
                for sound_name, path in sound_paths.items()
            }
        except Exception as error:
            raise RuntimeError("pygame audio backend initialization failed") from error

    def play(self, sound_name: str) -> None:
        sound = self._sounds.get(sound_name)
        if sound is None:
            return
        channel = pygame.mixer.find_channel(True)
        if channel is not None:
            channel.play(sound)
        else:
            sound.play()

    def close(self) -> None:
        try:
            pygame.mixer.quit()
        except Exception:
            return


class _CommandAudioBackend:
    def __init__(self, sound_paths: dict[str, Path]) -> None:
        self._command = self._resolve_command()
        self._sound_paths = sound_paths
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=32)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _resolve_command(self) -> list[str]:
        for command in COMMAND_BACKENDS:
            if shutil.which(command[0]):
                return command
        raise RuntimeError("no supported command-line audio backend is available")

    def _run(self) -> None:
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        while not self._stop_event.is_set():
            try:
                sound_name = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if sound_name is None:
                return

            path = self._sound_paths.get(sound_name)
            if path is None or not path.exists():
                continue

            try:
                subprocess.Popen(
                    [*self._command, str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except Exception:
                continue

    def play(self, sound_name: str) -> None:
        try:
            self._queue.put_nowait(sound_name)
        except queue.Full:
            return

    def close(self) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=0.2)


class SnakeAudio:
    def __init__(self, sounds_dir: Path | None = None) -> None:
        self._last_played_at: dict[str, float] = {}
        self._backend = _NullAudioBackend()
        base_dir = sounds_dir or Path(__file__).with_name("snake_sounds")
        self._sound_paths = {
            sound_name: base_dir / filename
            for sound_name, filename in SOUND_FILENAMES.items()
        }
        if not all(path.exists() for path in self._sound_paths.values()):
            return

        for backend_cls in (_PygameAudioBackend, _CommandAudioBackend):
            try:
                self._backend = backend_cls(self._sound_paths)
                return
            except Exception:
                continue

    def _play(self, sound_name: str) -> None:
        now = time.perf_counter()
        min_interval = MIN_INTERVAL_SECONDS.get(sound_name, 0.0)
        last_played_at = self._last_played_at.get(sound_name, 0.0)
        if min_interval > 0 and (now - last_played_at) < min_interval:
            return
        self._last_played_at[sound_name] = now
        self._backend.play(sound_name)

    def play_move(self) -> None:
        self._play("move")

    def play_food(self) -> None:
        self._play("food")

    def play_game_over(self) -> None:
        self._play("game_over")

    def close(self) -> None:
        self._backend.close()
