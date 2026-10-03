"""Against the real game: python -m pytest tests/integration (needs SPELUNKY2RL_GAME_DIR, Docker and the image).

SPELUNKY2RL_LAUNCHER picks the launcher (default: docker on Linux).
"""

import math
import subprocess
import time

import gymnasium as gym
import numpy as np
import pytest

from spelunky2rl.envs.default_environment import SpelunkyEnv as DefaultEnv
from spelunky2rl.envs.get_to_exit import SpelunkyEnv as GetToExit

FAST = {"speedup": True, "state_updates": 50}


def running_containers():
    out = subprocess.run(["docker", "ps", "--filter", "name=spelunky2rl-", "--format", "{{.Names}}"],
                         capture_output=True, text=True)
    return out.stdout.split()


def own_containers(envs):
    names = {env.launcher.container for env in envs if getattr(env.launcher, "container", None)}
    return names & set(running_containers())


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
    assert not own_containers([env])


def test_actions_move_the_player_and_are_deterministic():
    """The agent's input used to be ignored in ~40% of episodes (steal_input), which also made
    episodes non-reproducible."""
    env = GetToExit(**FAST, god_mode=True)

    def episode(seed):
        env.reset(seed=seed)
        xs = [env.last_gamestate["basic_info"]["x"]]
        for i in range(60):
            env.step([2 if (i // 30) % 2 == 0 else 0, 1, int(i % 8 == 0)])
            xs.append(env.last_gamestate["basic_info"]["x"])
        return xs

    try:
        for seed in range(8):
            first, second = episode(seed), episode(seed)
            assert max(first) - min(first) > 0.5, f"player did not move (seed {seed})"
            assert first == second, f"seed {seed} not reproducible"
    finally:
        env.close()


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


def test_dist_to_goal_follows_the_player_cell():
    """Between two steps dist_to_goal changes by at most the cells the player moved, with the same
    parity: same cell, same distance; next cell, one more or one less. The distance used to be
    read from the cell above (and often one to the left), where it froze against ceilings."""
    env = GetToExit(**FAST, god_mode=True)

    def cell_and_distance():
        info = env.last_gamestate["basic_info"]
        return math.floor(info["x"] + 0.5), math.floor(info["y"] + 0.5), env.last_gamestate["dist_to_goal"]

    try:
        for seed in range(4):
            actions = np.random.default_rng(seed).integers(0, [3, 3, 2], size=(300, 3))
            env.reset(seed=seed)
            x, y, distance = cell_and_distance()
            for step, action in enumerate(actions):
                env.step(action)
                new_x, new_y, new_distance = cell_and_distance()
                moved, change = abs(new_x - x) + abs(new_y - y), abs(new_distance - distance)
                assert change <= moved and (moved - change) % 2 == 0, (
                    f"seed {seed} step {step}: cell ({x}, {y}) -> ({new_x}, {new_y}), "
                    f"dist_to_goal {distance} -> {new_distance}")
                x, y, distance = new_x, new_y, new_distance
    finally:
        env.close()


def test_reset_leaves_nothing_of_the_previous_level():
    """Seeds 28 and 29 have the same number of floor tiles (1108), which used to keep the tiles,
    the distances and the exit of the previous level."""

    def first_state(env, seed):
        env.reset(seed=seed)
        return env.last_gamestate["dist_to_goal"], env.last_gamestate["map_info"]

    env = GetToExit(**FAST, god_mode=True)
    try:
        fresh = first_state(env, 29)
    finally:
        env.close()

    env = GetToExit(**FAST, god_mode=True)
    try:
        env.reset(seed=28)
        for i in range(50):
            env.step([2 if (i // 25) % 2 == 0 else 0, 1, int(i % 8 == 0)])
        assert first_state(env, 29) == fresh
    finally:
        env.close()


@pytest.mark.parametrize("n", [4])
def test_parallel_envs(n):
    before = set(running_containers())
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
    assert set(running_containers()) <= before


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
