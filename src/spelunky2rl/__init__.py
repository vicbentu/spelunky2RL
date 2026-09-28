import gymnasium as gym

from .engine import SpelunkyRLEngine
from .envs import *  # noqa: F403  (imports every env module)
from .tools import id2name

__all__ = ["SpelunkyRLEngine", "id2name"]

# gymnasium.make("spelunky2rl/GetToExit-v0", ...); every env handles its own time limit
ENV_IDS = {
    "spelunky2rl/Default-v0": "spelunky2rl.envs.default_environment:SpelunkyEnv",
    "spelunky2rl/Dummy-v0": "spelunky2rl.envs.dummy_environment:SpelunkyEnv",
    "spelunky2rl/GetToExit-v0": "spelunky2rl.envs.get_to_exit:SpelunkyEnv",
    "spelunky2rl/GoldGrabber-v0": "spelunky2rl.envs.gold_grabber:SpelunkyEnv",
    "spelunky2rl/EnemyKiller-v0": "spelunky2rl.envs.enemy_killer:SpelunkyEnv",
}
for _env_id, _entry_point in ENV_IDS.items():
    if _env_id not in gym.registry:
        gym.register(id=_env_id, entry_point=_entry_point)
