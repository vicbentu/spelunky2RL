import socket

import pytest

from fake_lua import FakeLua


@pytest.fixture
def make_env():
    """Build any SpelunkyEnv class wired to a FakeLua instead of a real game."""
    created = []

    def factory(env_cls, respond=None, **kwargs):
        engine_end, lua_end = socket.socketpair()

        class OfflineEnv(env_cls):
            def _game_init(self):
                self.server = engine_end
                self.server.settimeout(self.step_timeout)

        env = OfflineEnv(spelunky_dir="unused", playlunky_dir="unused", **kwargs)
        env.fake_lua = FakeLua(lua_end, respond)
        created.append(env)
        return env

    yield factory
    for env in created:
        env.close()
