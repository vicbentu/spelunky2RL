import os
import sys
from typing import Optional, Union

from .base import Launcher, PlaylunkyCache

LAUNCHERS = ("docker", "wine", "windows")


def make_launcher(launcher: Union[str, Launcher], game_dir: Optional[str], renderer: str = "auto",
                  console: bool = False, playlunky_dir: Optional[str] = None,
                  options: Optional[dict] = None) -> Launcher:
    """Build the launcher named by `launcher` ("auto", "docker", "wine", "windows"), or pass an instance through."""
    if isinstance(launcher, Launcher):
        return launcher
    options = dict(options or {})
    name = launcher
    if name == "auto":
        name = os.environ.get("SPELUNKY2RL_LAUNCHER") or ("windows" if sys.platform == "win32" else "docker")
    game_dir = game_dir or os.environ.get("SPELUNKY2RL_GAME_DIR")
    if not game_dir:
        raise ValueError("Where is Spelunky 2? Pass game_dir= (the folder with Spel2.exe) or set SPELUNKY2RL_GAME_DIR")

    if name == "docker":
        from .docker import DockerLauncher

        return DockerLauncher(game_dir, renderer=renderer, **options)
    if name == "wine":
        from .wine import WineLauncher

        return WineLauncher(game_dir, renderer=renderer, **options)
    if name == "windows":
        from .windows import WindowsLauncher

        return WindowsLauncher(game_dir, playlunky_dir=playlunky_dir, console=console, **options)
    raise ValueError(f"launcher must be 'auto', one of {LAUNCHERS}, or a Launcher instance; got {launcher!r}")


__all__ = ["LAUNCHERS", "Launcher", "PlaylunkyCache", "make_launcher"]
