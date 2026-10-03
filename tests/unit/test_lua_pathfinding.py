"""The BFS of mod/lua/spelunky2rl/pathfinding.lua, run with the system's Lua (skipped if there is none)."""

import shutil
import subprocess
from importlib.resources import files

import pytest

LUA = shutil.which("lua5.4") or shutil.which("lua")
LUA_DIR = files("spelunky2rl") / "mod" / "lua"

pytestmark = pytest.mark.skipif(LUA is None, reason="needs a Lua interpreter (lua5.4 or lua)")

SCRIPT = """
package.path = arg[1] .. "/?.lua;" .. package.path
local pathfinding = require("spelunky2rl.pathfinding")
local field = pathfinding.distance_field({board}, {goals})
for _, row in ipairs(field) do print(table.concat(row, " ")) end
"""


def distance_field(board, goals):
    """`board` as rows of text, '#' = solid; `goals` as (column, row) pairs, both from 1 like in Lua."""
    rows = ",".join("{" + ",".join("1" if cell == "#" else "0" for cell in row) + "}" for row in board)
    goals = ",".join(f"{{{column},{row}}}" for column, row in goals)
    script = SCRIPT.format(board="{" + rows + "}", goals="{" + goals + "}")
    out = subprocess.run([LUA, "-", str(LUA_DIR)], input=script, capture_output=True, text=True, check=True)
    return [[int(cell) for cell in line.split()] for line in out.stdout.splitlines()]


def test_open_board_gives_manhattan_distances():
    assert distance_field(["...", "...", "..."], goals=[(1, 1)]) == [[0, 1, 2], [1, 2, 3], [2, 3, 4]]


def test_walks_around_solid_cells():
    board = [".#...",
             ".#.#.",
             "...#."]
    assert distance_field(board, goals=[(1, 1)]) == [[0, -1, 6, 7, 8],
                                                     [1, -1, 5, -1, 9],
                                                     [2, 3, 4, -1, 10]]


def test_cells_cut_off_from_the_goal_are_unreachable():
    board = ["..#..",
             "..#.."]
    assert distance_field(board, goals=[(5, 2)]) == [[-1, -1, -1, 2, 1],
                                                     [-1, -1, -1, 1, 0]]


def test_every_cell_takes_the_nearest_goal():
    assert distance_field([".....", "....."], goals=[(1, 1), (5, 2)]) == [[0, 1, 2, 2, 1],
                                                                         [1, 2, 2, 1, 0]]


def test_a_goal_outside_the_board_is_ignored():
    assert distance_field(["..."], goals=[(0, 1), (3, 1), (2, 5)]) == [[2, 1, 0]]


def test_no_goal_leaves_every_cell_unreachable():
    assert distance_field(["..#", "..."], goals=[]) == [[-1, -1, -1], [-1, -1, -1]]
