"""Golden trace of the Lua mod: every raw message it sends over a fixed set of episodes.

    python tests/integration/golden.py record     # save the trace of the mod as it is now
    python tests/integration/golden.py compare    # run the same episodes, demand the same messages

Needs SPELUNKY2RL_GAME_DIR, Docker and the game image, like test_game.py. The mod under test is
--mod (default: src/spelunky2rl/mod/lua of this checkout), mounted over the one in the image, so
a Lua change is checked without rebuilding. The game is deterministic for a given seed and input,
so any difference is a change of behaviour: record before a refactor of the mod, compare after
every step. A change that is meant to alter the messages needs a new recording.

Two messages are the same when they have the same fields with the same values, numbers compared
as the text the mod wrote. The order of the keys is not compared: Lua's json.encode follows the
table's internal order, which changes from one game process to the next.

All episodes run in order in one game instance: what the mod carries over from one episode to the
next is part of the trace. The trace is only valid for one game build and one Overlunky build.
"""

import argparse
import gzip
import json
import os
import random
import sys
import time
from pathlib import Path

from spelunky2rl.envs.default_environment import SpelunkyEnv as DefaultEnv
from spelunky2rl.envs.get_to_exit import SpelunkyEnv as GetToExit

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MOD = REPO / "src" / "spelunky2rl" / "mod" / "lua"
DEFAULT_TRACE = Path(__file__).resolve().parent / "data" / "golden_trace.jsonl.gz"

BASE = {"speedup": True, "state_updates": 50}


def case(name, seed=0, steps=300, frames_per_step=6, bomb_rope=0.02, script=None, **options):
    """An episode: `steps` pseudo-random actions drawn from `seed`, or the actions in `script`."""
    return {"name": name, "seed": seed, "steps": steps, "frames_per_step": frames_per_step,
            "bomb_rope": bomb_rope, "script": script, "options": BASE | options}


def exit_script():
    """Seed 268: bomb straight down to the exit, enter it and play on in 1-2. Found by search;
    only valid while the game stays deterministic, like the rest of the trace."""
    def a(x=1, y=1, jump=0, bomb=0, run=1, door=0):
        return [x, y, jump, 0, bomb, 0, run, door]

    script = [a(x=2)] * 6 + [a(x=0, jump=1)] * 3 + [a(x=0)] * 4
    script += ([a(y=0, bomb=1)] + [a()] * 26) * 3
    script += [a(door=1)] * 2 + [a()] * 9  # the mod reports win=1 in the last of these
    script += [a(jump=int(i % 4 == 0), run=0) for i in range(30)]  # a jump leaves the transition screen
    script += [a(x=2 if (i // 20) % 2 == 0 else 0, jump=int(i % 8 == 0)) for i in range(80)]
    return script


# Episodes are not cut when the player leaves the level: the steps after an exit cover the transition
# and the next level. After a death they go on for FRAMES_AFTER_DEATH and stop there: a reset from
# the death screen (about 150 frames after dying) leaves the game stuck.
FRAMES_AFTER_DEATH = 60

CASES = (
    [case(f"seed{seed}", seed=seed) for seed in range(5)]
    + [case(f"seed{seed}_god", seed=seed, god_mode=True) for seed in range(5)]
    + [case("world2", world=2, steps=150, god_mode=True),
       case("world3", world=3, steps=150, god_mode=True),
       case("world4", world=4, steps=150, god_mode=True),
       case("world6_level4", world=6, level=4, steps=150, god_mode=True),
       case("world2_volcana", world=2, theme=3, steps=150, god_mode=True),
       case("start_values", hp=8, bombs=1, ropes=0, gold=500, steps=150),
       case("destroy_entities", steps=150, god_mode=True,
            ent_types_to_destroy=GetToExit.reset_options["ent_types_to_destroy"]),
       case("state_updates_0", seed=1, god_mode=True, state_updates=0),
       case("state_updates_200", seed=1, god_mode=True, state_updates=200),
       case("no_speedup", seed=1, steps=60, god_mode=True, speedup=False),
       # a person plays: the actions must not reach the game
       case("manual_control", seed=1, steps=60, god_mode=True, manual_control=True),
       case("frames_per_step_1", seed=2, frames_per_step=1, god_mode=True),
       case("frames_per_step_12", seed=2, frames_per_step=12, god_mode=True),
       # floor tiles destroyed all along the episode: the tile table and the distance field are rebuilt
       case("bombs_and_ropes", seed=3, god_mode=True, bombs=99, ropes=99, bomb_rope=0.15),
       # win, the transition screen and a second level in the same episode
       case("exit_and_next_level", seed=268, god_mode=True, script=exit_script())]
)


def actions(seed, steps, bomb_rope):
    """Full action space, with the direction held for a while so that the player gets somewhere."""
    rng = random.Random(seed)
    action = [rng.randrange(3), 1, 0, 0, 0, 0, 1, 0]
    for _ in range(steps):
        if rng.random() < 0.15:
            action[0] = rng.randrange(3)
        if rng.random() < 0.15:
            action[1] = rng.randrange(3)
        action[2] = int(rng.random() < 0.3)        # jump
        action[3] = int(rng.random() < 0.1)        # whip
        action[4] = int(rng.random() < bomb_rope)  # bomb
        action[5] = int(rng.random() < bomb_rope)  # rope
        if rng.random() < 0.1:
            action[6] = rng.randrange(2)           # run
        action[7] = int(rng.random() < 0.1)        # door
        yield list(action)


class Tap:
    """Stands in for the engine's socket and keeps every byte the mod sends."""

    def __init__(self, sock):
        self._sock = sock
        self._data = bytearray()

    def recv(self, size):
        chunk = self._sock.recv(size)
        self._data += chunk
        return chunk

    def take(self):
        """The complete messages received since the last call, as raw lines."""
        *lines, rest = bytes(self._data).split(b"\n")
        self._data = bytearray(rest)
        return [line.decode("utf-8") for line in lines]

    def __getattr__(self, name):
        return getattr(self._sock, name)


def run(mod):
    """Play every case and return {name: [raw message, ...]}: the reset state, then one per step."""
    os.environ["SPELUNKY2RL_DEV_MOD"] = str(mod)
    env = DefaultEnv()
    trace = {}
    try:
        tap = env.server.sock = Tap(env.server.sock)
        for c in CASES:
            start = time.monotonic()
            env.frames_per_step = c["frames_per_step"]
            env.reset(seed=c["seed"], **c["options"])
            dead_frames = 0
            for action in c["script"] or actions(c["seed"], c["steps"], c["bomb_rope"]):
                env.step(action)
                if env.last_gamestate["basic_info"]["health"] <= 0 and not c["options"].get("god_mode"):
                    dead_frames += c["frames_per_step"]
                    if dead_frames >= FRAMES_AFTER_DEATH:
                        break
            trace[c["name"]] = tap.take()
            last = env.last_gamestate["basic_info"]
            print(f"  {c['name']:<20} {len(trace[c['name']]):>4} messages in {time.monotonic() - start:5.1f} s"
                  f"   ends at {last['world']}-{last['level']} health={last['health']}", flush=True)
    finally:
        env.close()
    return trace


def save(trace, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for name, messages in trace.items():
            f.write(json.dumps({"golden_case": name, "messages": len(messages)}) + "\n")
            for message in messages:
                f.write(message + "\n")


def load(path):
    trace = {}
    with gzip.open(path, "rt", encoding="utf-8") as f:
        lines = iter(f.read().splitlines())
    for line in lines:
        header = json.loads(line)
        trace[header["golden_case"]] = [next(lines) for _ in range(header["messages"])]
    return trace


def first_difference(expected, got, path=""):
    """Path and values of the first field that differs between two decoded messages, or None."""
    if isinstance(expected, dict) and isinstance(got, dict):
        for key in sorted(set(expected) | set(got)):
            if key not in expected or key not in got:
                return f"{path}.{key}".lstrip("."), expected.get(key, "<missing>"), got.get(key, "<missing>")
            diff = first_difference(expected[key], got[key], f"{path}.{key}")
            if diff:
                return diff
        return None
    if isinstance(expected, list) and isinstance(got, list):
        if len(expected) != len(got):
            return f"{path}.length".lstrip("."), len(expected), len(got)
        for i, (a, b) in enumerate(zip(expected, got)):
            diff = first_difference(a, b, f"{path}[{i}]")
            if diff:
                return diff
        return None
    if type(expected) is not type(got) or expected != got:
        return path.lstrip("."), expected, got
    return None


class Number(str):
    """A JSON number kept as the text the mod wrote, so 1 and 1.0 are different values."""

    __repr__ = str.__str__


def decode(message):
    return json.loads(message, parse_int=Number, parse_float=Number)


def describe_difference(expected, got):
    """First difference between two lists of raw messages, as text, or None if they are identical."""
    for i, (a, b) in enumerate(zip(expected, got)):
        if a == b:
            continue
        diff = first_difference(decode(a), decode(b))
        if diff is None:
            continue  # only the order of the keys
        field, old, new = diff
        where = f"message {i} ({'reset state' if i == 0 else f'step {i}'})"
        return f"{where}, field {field}: expected {old!r}, got {new!r}"
    if len(expected) != len(got):
        return f"{len(got)} messages, expected {len(expected)}"
    return None


def compare(expected, got):
    different = 0
    for name in list(expected) + [n for n in got if n not in expected]:
        if name not in expected or name not in got:
            diff = "missing in the " + ("recorded trace" if name not in expected else "new run")
        else:
            diff = describe_difference(expected[name], got[name])
        if diff is not None:
            different += 1
            print(f"  DIFF {name}: {diff}")
    total = sum(len(messages) for messages in expected.values())
    if different:
        print(f"FAILED: {different} of {len(expected)} episodes differ from the recorded trace")
    else:
        print(f"OK: {len(expected)} episodes, {total} messages, all identical")
    return different == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", choices=["record", "compare"])
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE, help=f"default: {DEFAULT_TRACE}")
    parser.add_argument("--mod", type=Path, default=DEFAULT_MOD, help="lua/ folder with the mod to run")
    parser.add_argument("--save-run", type=Path, help="compare: also write the new run to this file")
    args = parser.parse_args()

    if not os.environ.get("SPELUNKY2RL_GAME_DIR"):
        sys.exit("Set SPELUNKY2RL_GAME_DIR to the Spelunky 2 folder")
    if args.mode == "compare" and not args.trace.is_file():
        sys.exit(f"No recorded trace at {args.trace}: run `golden.py record` with the reference mod first")

    print(f"Running {len(CASES)} episodes with the mod in {args.mod}")
    trace = run(args.mod)

    if args.mode == "record":
        save(trace, args.trace)
        print(f"Recorded {sum(map(len, trace.values()))} messages in {args.trace} "
              f"({args.trace.stat().st_size / 1e6:.1f} MB)")
        return
    if args.save_run:
        save(trace, args.save_run)
    sys.exit(0 if compare(load(args.trace), trace) else 1)


if __name__ == "__main__":
    main()
