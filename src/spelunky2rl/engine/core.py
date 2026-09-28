import os
import socket
import subprocess
import json
import atexit
import psutil
import time
from datetime import datetime
from typing import Any, Dict, Tuple, List, Optional
from collections import Counter

import gymnasium as gym
import numpy as np

from ..tools.id2name import id2name


class SpelunkyRLEngine(gym.Env):

    ############## GYM interface ##############

    action_space: gym.spaces.MultiDiscrete = gym.spaces.MultiDiscrete([
        3, # Movement X
        3, # Movement Y
        2, # Jump
        2, # Whip
        2, # Bomb
        2, # Rope
        2, # Run
        2, # Door
    ])

    observation_space: gym.spaces.Dict

    def __init__(
            self,
            spelunky_dir: str,
            playlunky_dir: str,
            frames_per_step: int = 6,
            render_enabled: bool = False,
            console: bool = False,
            log_file: str = None,
            log_info: Optional[List[str]] = None,
            step_timeout: float = 60.0,
            startup_timeout: float = 180.0,
            max_launch_attempts: int = 3,
            **kwargs
        ) -> None:

        super().__init__()

        self.spelunky_dir = spelunky_dir
        self.playlunky_dir = playlunky_dir
        self.frames_per_step = frames_per_step
        self.reset_options = getattr(self, "reset_options", {}) | kwargs
        self.render_enabled = render_enabled
        self.render_mode = 'rgb_array'
        self.console = console
        self.log_file = log_file
        self.log_info = log_info if log_info is not None else ["all"]
        self.step_timeout = step_timeout
        self.startup_timeout = startup_timeout
        self.max_launch_attempts = max_launch_attempts
        self._closed = False

        self._game_init()


    # TODO: items, powerups
    def reset(
        self,
        *,
        seed: Optional[int] = None,
        **kwargs
    ) -> Tuple[Dict, Dict[str, Any]]:

        super().reset(seed=seed)
        self._game_reset(seed=seed, **(self.reset_options|kwargs))

        gamestate = self._receive_dict()
        self.last_gamestate = gamestate
        observation = self.gamestate_to_observation(gamestate)
        return observation, {}


    def step(
        self, action: Any
    ) -> Tuple[Dict, float, bool, bool, Dict[str, Any]]:

        action = np.asarray(action).tolist()
        if hasattr(self, 'action_to_input'):
            action = self.action_to_input(action)
        self._send_dict({
            "command": "step",
            "input": action,
            "frames": self.frames_per_step,
            "data_to_send": getattr(self, "data_to_send", [])
        })

        gamestate = self._receive_dict()

        info = {
            "success": False
        }

        if self.log_file:
            self.log_step(gamestate)

        reward, done, truncated, info = self.reward_function(gamestate, self.last_gamestate, action, info)
        done = done or bool(gamestate["basic_info"]["health"] <= 0 or gamestate["basic_info"]["win"] == 1)
        self.last_gamestate = gamestate
        observation = self.gamestate_to_observation(gamestate)

        return observation, reward, done, truncated, info



    ############ Spelunky  Communicaton ############

    def close(self):
        if getattr(self, "_closed", True):
            return
        self._closed = True
        atexit.unregister(self.close)

        server = getattr(self, "server", None)
        if server is not None:
            try:
                self._send_dict({"command": "close"})
            except OSError:
                pass
            server.close()
        if getattr(self, "server_socket", None) is not None:
            self.server_socket.close()
        if getattr(self, "grabber", None) is not None:
            self.grabber.stop()

        for process in (getattr(self, "game_process", None), getattr(self, "launcher_process", None)):
            if process is None:
                continue
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

    def _game_init(self):

        executable_path = os.path.join(self.playlunky_dir, "playlunky_launcher.exe")
        args = [
            f'-exe_dir={self.spelunky_dir}',
            *(['-console'] if self.console else [])
        ]

        load_order_path = os.path.join(self.spelunky_dir, "Mods", "Packs", "load_order.txt")
        with open(load_order_path, "w") as f:
            f.write("spelunky2rl\n")


        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('127.0.0.1', 0))
        self.server_socket.listen(1)
        port = self.server_socket.getsockname()[1]
        os.environ["Spelunky_RL_Port"] = str(port)

        def launch():
            return subprocess.Popen([executable_path] + args, cwd=self.playlunky_dir)

        self.launcher_process = launch()
        launch_attempts = 1
        self.game_process = None
        self.server_socket.settimeout(0.05)
        atexit.register(self.close)
        deadline = time.monotonic() + self.startup_timeout

        while True:
            try:
                self.server, addr = self.server_socket.accept()
                break
            except socket.timeout:
                pass

            if time.monotonic() > deadline:
                self.close()
                raise TimeoutError(f"Spelunky 2 did not connect within {self.startup_timeout} s")

            if self.game_process is not None and self.game_process.is_running():
                pass
            else:
                if self.launcher_process.poll() is None:
                    parent = psutil.Process(self.launcher_process.pid)
                    children = parent.children(recursive=True)
                    for child in children:
                        if child.name().startswith("Spel2"):
                            self.game_process = child

                elif launch_attempts < self.max_launch_attempts:
                    self.launcher_process = launch()
                    launch_attempts += 1
                else:
                    self.close()
                    raise RuntimeError(f"Playlunky exited {launch_attempts} times before the game connected")

        self.server.settimeout(self.step_timeout)
        if self.render_enabled:
            # Windows-only modules, imported here so the package imports on any platform
            import win32gui
            from .utils.frame_grabber import FrameGrabber
            from .utils.window_management import get_hwnd_for_pid

            self.hwnd = get_hwnd_for_pid(self.game_process.pid)
            self.grabber = FrameGrabber(self.hwnd)
            current_title = win32gui.GetWindowText(self.hwnd)
            new_title = f"R_{current_title}"
            win32gui.SetWindowText(self.hwnd, new_title)

    def _game_reset(
            self,
            seed:int = None,
            speedup: bool = False,
            state_updates: int = 0,

            ent_types_to_destroy = (),
            manual_control: bool = False,
            god_mode: bool = False,
            hp: int = 4,
            bombs: int = 4,
            ropes: int = 4,
            gold: int = 0,
            world: int = 1,
            level: int = 1,
            theme: Optional[int] = None,
            **kwargs
        ) -> None:

        if seed is None:
            seed = int(self.np_random.integers(0, 2**32))
        message = {
            "command": "reset",
            "speedup": speedup,
            "state_updates": state_updates,
            "seed": seed,
            "ent_types_to_destroy": list(ent_types_to_destroy),
            "data_to_send": self.data_to_send,
            "manual_control": manual_control,
            "god_mode": god_mode,
            "hp": hp,
            "bombs": bombs,
            "ropes": ropes,
            "gold": gold,
            "world": world,
            "level": level
        }
        # Lua picks the world's default theme; pass a THEME value to choose e.g. Volcana (3) or Temple (6)
        if theme is not None:
            message["theme"] = theme
        self._send_dict(message)

    def _send_dict(self, payload: Dict[str, Any]) -> None:
        json_str = json.dumps(payload) + "\n"
        self.server.sendall(json_str.encode("utf-8"))

    def _receive_dict(self) -> Dict[str, Any]:
        buffer = b""
        while not buffer.endswith(b"\n"):
            try:
                data = self.server.recv(1024)
            except socket.timeout:
                raise TimeoutError(f"No response from the Spelunky Lua script in {self.step_timeout} s") from None
            if not data:
                raise ConnectionError("Disconnected from Spelunky Lua script")
            buffer += data
        json_str = buffer.decode("utf-8").strip()
        dict = json.loads(json_str)
        if "error" in dict:
            raise RuntimeError(dict["error"])

        return dict


    ############ Render ############

    metadata = {"render_modes": ["rgb_array"], "render_fps": 60}

    def render(self, mode="rgb_array"):
        if mode != "rgb_array":
            raise NotImplementedError
        if self.render_enabled is False:
            raise RuntimeError("Use render_enabled=True on init to be able to record replays")

        return self.grabber.get_frame()



    ########### Log ################

    def log_step(self, gamestate):
        with open(self.log_file, "a") as f:
            f.write("----------------------------------\n")
            for field in self.log_info:
                if field == "all":
                    timestamp = datetime.now().strftime("%H:%M:%S:%f")[:-3]
                    f.write(f"-- {timestamp} {str(gamestate)}\n")
                if field == "map_info":
                    f.write(str(gamestate["map_info"]) + "\n")
                    for row in gamestate["map_info"]:
                        formatted_row = " ".join(f"{cell:>3}" for cell in row)
                        f.write(f"{formatted_row}\n")
                elif field == "entity_count":
                    type_counts = Counter(id2name(entity[4])["name"] for entity in gamestate["entity_info"])
                    f.write(f"Entities: {type_counts}\n")
