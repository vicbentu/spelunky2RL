"""The BFS of mod/lua/spelunky2rl/pathfinding.lua, run with the system's Lua (skipped if there is none)."""

import shutil
import subprocess
from importlib.resources import files

import pytest

LUA = shutil.which("lua5.4") or shutil.which("lua")
PATHFINDING = files("spelunky2rl") / "mod" / "lua" / "spelunky2rl" / "pathfinding.lua"

pytestmark = pytest.mark.skipif(LUA is None, reason="needs a Lua interpreter (lua5.4 or lua)")

SCRIPT = """
local pathfinding = dofile(arg[1])
local field = pathfinding.distance_field({board}, {goal_x}, {goal_y})
for _, row in ipairs(field) do print(table.concat(row, " ")) end
"""


def distance_field(board, goal):
    """`board` as rows of text, '#' = solid; `goal` as (column, row), both from 1 like in Lua."""
    rows = ",".join("{" + ",".join("1" if cell == "#" else "0" for cell in row) + "}" for row in board)
    script = SCRIPT.format(board="{" + rows + "}", goal_x=goal[0], goal_y=goal[1])
    out = subprocess.run([LUA, "-", str(PATHFINDING)], input=script, capture_output=True, text=True, check=True)
    return [[int(cell) for cell in line.split()] for line in out.stdout.splitlines()]


def test_open_board_gives_manhattan_distances():
    assert distance_field(["...", "...", "..."], goal=(1, 1)) == [[0, 1, 2], [1, 2, 3], [2, 3, 4]]


def test_walks_around_solid_cells():
    board = [".#...",
             ".#.#.",
             "...#."]
    assert distance_field(board, goal=(1, 1)) == [[0, -1, 6, 7, 8],
                                                  [1, -1, 5, -1, 9],
                                                  [2, 3, 4, -1, 10]]


def test_cells_cut_off_from_the_goal_are_unreachable():
    board = ["..#..",
             "..#.."]
    assert distance_field(board, goal=(5, 2)) == [[-1, -1, -1, 2, 1],
                                                  [-1, -1, -1, 1, 0]]
