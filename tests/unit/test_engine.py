from importlib.resources import files

import numpy as np
import pytest

import spelunky2rl
from spelunky2rl.envs.default_environment import SpelunkyEnv as DefaultEnv
from spelunky2rl.envs.get_to_exit import SpelunkyEnv as GetToExit


def sent_seeds(env):
    return [m["seed"] for m in env.fake_lua.messages if m["command"] == "reset"]


def test_seeds_are_reproducible(make_env):
    a, b = make_env(DefaultEnv), make_env(DefaultEnv)
    for env in (a, b):
        env.reset(seed=123)
        env.reset()
        env.reset()
    assert sent_seeds(a)[0] == 123
    assert sent_seeds(a) == sent_seeds(b)
    assert len(set(sent_seeds(a))) == 3


def test_unseeded_resets_differ_between_envs(make_env):
    a, b = make_env(DefaultEnv), make_env(DefaultEnv)
    a.reset()
    b.reset()
    assert sent_seeds(a) != sent_seeds(b)


def test_reset_options_reach_lua(make_env):
    env = make_env(DefaultEnv, hp=8)
    env.reset(seed=0, world=3, theme=4)
    message = env.fake_lua.messages[-1]
    assert (message["hp"], message["world"], message["theme"]) == (8, 3, 4)
    env.reset(seed=0)
    assert "theme" not in env.fake_lua.messages[-1]


def test_headless_defaults_reach_lua(make_env):
    env = make_env(DefaultEnv)
    env.reset(seed=0)
    message = env.fake_lua.messages[-1]
    assert message["render"] is False and message["vsync"] is False and message["audio"] is False
    assert message["time_ghost"] is True
    env.reset(seed=0, time_ghost=False)
    assert env.fake_lua.messages[-1]["time_ghost"] is False


@pytest.mark.parametrize("action", [[2, 1, 1], (2, 1, 1), np.array([2, 1, 1])])
def test_action_types(make_env, action):
    env = make_env(GetToExit)
    env.reset(seed=0)
    env.step(action)
    assert env.fake_lua.messages[-1]["input"] == [2, 1, 1, 0, 0, 0, 1, 0]


def test_lua_error_is_raised(make_env):
    env = make_env(DefaultEnv, respond=lambda message, steps: {"error": "Invalid world number: 99"})
    with pytest.raises(RuntimeError, match="Invalid world"):
        env.reset(seed=0)


def test_silent_game_times_out(make_env):
    env = make_env(DefaultEnv, respond=lambda message, steps: None, step_timeout=0.2)
    with pytest.raises(TimeoutError):
        env.reset(seed=0)


def test_close_is_idempotent(make_env):
    env = make_env(DefaultEnv)
    env.reset(seed=0)
    env.close()
    env.close()
    env.fake_lua.join(timeout=2)
    commands = [m["command"] for m in env.fake_lua.messages]
    assert commands.count("close") == 1


def test_close_survives_dead_game(make_env):
    env = make_env(DefaultEnv)
    env.reset(seed=0)
    env.fake_lua.sock.close()
    env.close()


def test_package_ships_the_mod_and_entity_names():
    assert (files("spelunky2rl") / "mod" / "lua" / "main.lua").is_file()
    assert (files("spelunky2rl") / "mod" / "lua" / "luasocket" / "socket_core.dll").is_file()
    assert spelunky2rl.id2name(23)["name"] == "FLOOR_DOOR_EXIT"
