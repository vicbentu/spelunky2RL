import filecmp
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..assemble import config_dir, mod_dir
from ..frames import FrameSource
from .base import PORT_ENV, Launcher, check_game_dir, find_game_process, terminate

OVERLUNKY_SETTINGS = {
    # Playlunky always starts meta.unsafe scripts disabled; Overlunky can autorun them
    "autorun_scripts": '["main.lua"]',
    "script_dir": '"Mods/Packs/spelunky2rl/lua"',
    "enable_unsafe_scripts": "1",
}


def set_ini_values(text: str, values: dict) -> str:
    """Set top-level `key = value` entries of overlunky.ini, including multi-line arrays."""
    for key, value in values.items():
        pattern = re.compile(rf"^{key}\s*=\s*(\[[^\]]*\]|[^\n]*)", re.MULTILINE)
        line = f"{key} = {value}"
        if pattern.search(text):
            text = pattern.sub(lambda _match, line=line: line, text, count=1)
        else:
            text = text.rstrip("\n") + f"\n{line}\n"
    return text


def install_mod(game_dir: Path) -> None:
    """Put the bundled mod pack in the game's Mods/Packs and make Overlunky autorun it."""
    pack = game_dir / "Mods" / "Packs" / "spelunky2rl"
    source = mod_dir()
    if not pack.exists() or filecmp.dircmp(source / "lua", pack / "lua").diff_files:
        shutil.copytree(source, pack, dirs_exist_ok=True)
    (game_dir / "Mods" / "Packs" / "load_order.txt").write_text("spelunky2rl\n")

    ini = game_dir / "overlunky.ini"
    if ini.exists():
        ini.write_text(set_ini_values(ini.read_text(), OVERLUNKY_SETTINGS))
    else:
        shutil.copy(config_dir() / "overlunky.ini", ini)


class WindowsLauncher(Launcher):
    """Runs the game natively on Windows through Playlunky (as installed by modlunky2).

    Works in the game folder itself, like before the Linux port: installs the mod pack, sets
    load_order.txt to only this mod, and sets the three Overlunky options that autorun main.lua.
    """

    def __init__(self, game_dir, playlunky_dir: Optional[str] = None, console: bool = False):
        self.game_dir = check_game_dir(game_dir)
        playlunky_dir = playlunky_dir or os.environ.get("SPELUNKY2RL_PLAYLUNKY_DIR")
        if not playlunky_dir or not (Path(playlunky_dir) / "playlunky_launcher.exe").is_file():
            raise FileNotFoundError("playlunky_dir must be a folder with playlunky_launcher.exe (modlunky2 keeps "
                                    "them under its data directory, playlunky/<version>); or set "
                                    "SPELUNKY2RL_PLAYLUNKY_DIR")
        if not (self.game_dir / "Overlunky" / "Overlunky.dll").is_file():
            raise FileNotFoundError(f"No Overlunky/Overlunky.dll in {self.game_dir}: install Overlunky from "
                                    "modlunky2's Overlunky tab")
        self.playlunky_dir = Path(playlunky_dir)
        self.console = console
        self.port = None
        self._launcher = None
        self._game = None
        install_mod(self.game_dir)

    def start(self, port: int) -> None:
        self.port = port
        self._game = None
        args = [str(self.playlunky_dir / "playlunky_launcher.exe"), f"--exe_dir={self.game_dir}", "--overlunky"]
        if self.console:
            args.append("--console")
        env = dict(os.environ, **{PORT_ENV: str(port)})
        self._launcher = subprocess.Popen(args, cwd=self.playlunky_dir, env=env)

    def is_running(self) -> bool:
        if self._game is None:
            self._game = find_game_process(self.port)
        if self._game is not None:
            return self._game.is_running()
        return self._launcher is not None and self._launcher.poll() is None

    def stop(self) -> None:
        if self._game is None and self.port is not None:
            self._game = find_game_process(self.port)
        terminate(self._game)
        terminate(self._launcher)
        self._game = self._launcher = None

    def frame_source(self) -> FrameSource:
        from ..frames.win32 import Win32FrameSource

        if self._game is None:
            self._game = find_game_process(self.port)
        return Win32FrameSource(self._game.pid)
