"""Against the real game: python -m pytest tests/integration (needs SPELUNKY2RL_GAME_DIR, Docker and the image).

SPELUNKY2RL_LAUNCHER picks the launcher (default: docker on Linux).
"""

import subprocess
import time

import gymnasium as gym
import pytest

from spelunky2rl.envs.default_environment import SpelunkyEnv as DefaultEnv
from spelunky2rl.envs.get_to_exit import SpelunkyEnv as GetToExit

FAST = {"speedup": True, "state_updates": 50}


def running_containers():
    out = subprocess.run(["docker", "ps", "--filter", "name=spelunky2rl-", "--format", "{{.Names}}"],
                         capture_output=True, text=True)
    return out.stdout.split()


def test_episode_and_cleanup():
    env = DefaultEnv(**FAST)
    try:
        assert env.mod_version
        obs, _ = env.reset(seed=3)
        assert env.observation_space.contains(obs)
        for _ in range(300):
            obs, reward, terminated, truncated, _ = env.step(env.action_space.sample())
            assert env.observation_space.contains(obs)
            if terminated or truncated:
                env.reset()
    finally:
        env.close()
    time.sleep(1)
    assert not running_containers()


def test_same_seed_same_level():
    env = GetToExit(**FAST)
    try:
        firsts = []
        for _ in range(2):
            env.reset(seed=42)
            firsts.append(env.last_gamestate["dist_to_goal"])
            env.reset(seed=7)
        assert firsts[0] == firsts[1]
    finally:
        env.close()


@pytest.mark.parametrize("n", [4])
def test_parallel_envs(n):
    envs = gym.vector.AsyncVectorEnv([lambda: GetToExit(**FAST) for _ in range(n)])
    try:
        envs.reset(seed=0)
        start = time.monotonic()
        for _ in range(500):
            envs.step(envs.action_space.sample())
        print(f"{n} envs: {500 * n / (time.monotonic() - start):.0f} steps/s total")
    finally:
        envs.close()
    time.sleep(1)
    assert not running_containers()


def test_render_returns_game_frames():
    pytest.importorskip("mss")
    env = GetToExit(render_enabled=True, god_mode=True)
    try:
        env.reset(seed=3)
        for _ in range(10):
            env.step([2, 1, 0])
        frame = env.render()
        assert frame.dtype.name == "uint8" and frame.shape == (360, 640, 3)
        # a black frame means the game is not presenting (e.g. fullscreen under Xvfb)
        assert frame.mean() > 20
    finally:
        env.close()
