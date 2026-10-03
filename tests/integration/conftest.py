import os

import pytest


def pytest_collection_modifyitems(config, items):
    if not os.environ.get("SPELUNKY2RL_GAME_DIR"):
        skip = pytest.mark.skip(reason="set SPELUNKY2RL_GAME_DIR to run tests against the real game")
        for item in items:
            item.add_marker(skip)
