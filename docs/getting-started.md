# Getting Started with SpelunkyRL

This guide will walk you through installing and running your first SpelunkyRL environment.

SpelunkyRL drives a real copy of Spelunky 2. Python runs where you train; each environment
starts its own game instance and closes it on `env.close()`. There are two ways to run the game:

| | Linux (recommended) | Windows |
|---|---|---|
| How the game runs | one Docker container per environment, headless | natively, with a window per environment |
| What you install | Docker (+ NVIDIA Container Toolkit for GPU) | modlunky2, Playlunky, Overlunky |
| Steam at runtime | no | no (use a separate modding copy) |

## You need your own copy of the game

Spelunky 2 is not included anywhere, including the Docker image. Buy it on Steam, install it once,
and copy the whole folder (the one with `Spel2.exe`) somewhere else. Use that copy for SpelunkyRL:
modding tools should never touch your Steam installation. Steam is not needed after that: on Linux
the image swaps in the [Goldberg emulator](https://github.com/Detanup01/gbe_fork) for the Steam API.

Then tell SpelunkyRL where the copy is, once:

```bash
export SPELUNKY2RL_GAME_DIR="/path/to/Spelunky 2"      # Linux
setx SPELUNKY2RL_GAME_DIR "C:\Games\Spelunky 2"       # Windows (new terminals)
```

or pass `game_dir="..."` when creating an environment.

## Installation on Linux (Docker)

1. Install [Docker Engine](https://docs.docker.com/engine/install/) and make sure your user can run
   `docker` without sudo. For GPU rendering also install the
   [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/);
   without it the game renders on the CPU (slower with many instances, but works).
2. Install the package (Python 3.9+, in a virtual environment):

   ```bash
   git clone https://github.com/vicbentu/spelunky2RL.git
   cd spelunky2RL
   pip install .              # add [render] for render(), [train] for the training examples
   ```

3. Get the game image. Either pull it, or build it from the repo (a few minutes):

   ```bash
   spelunky2rl pull
   # or: docker build -f docker/Dockerfile -t ghcr.io/vicbentu/spelunky2rl-game:$(python -c "import spelunky2rl.version as v; print(v.__version__)") .
   ```

4. Check everything:

   ```bash
   spelunky2rl doctor
   ```

Each environment then runs `docker run --rm ...` on creation and kills its container on `close()`.
Nothing keeps running when no environment is open. The first start of a new game version takes
~20 s while Playlunky builds its asset cache in `~/.cache/spelunky2rl`; later starts take ~8 s.

**Without Docker** (development): `scripts/setup_wine.sh` installs the same pieces for the host's Wine,
then use `launcher="wine"` or `SPELUNKY2RL_LAUNCHER=wine`.

**Editing the Lua mod**: set `SPELUNKY2RL_DEV_MOD=/path/to/spelunky2RL/src/spelunky2rl/mod/lua` and new
environments load it instead of the copy in the image; no rebuild needed.

## Installation on Windows

1. Install [modlunky2](https://github.com/spelunky-fyi/modlunky2) and point it at your modding copy.
   In its Overlunky tab, install Overlunky. Playlunky is installed by modlunky2.
2. Find the Playlunky folder: in modlunky2, Settings → User Directories → Data, then
   `playlunky/<version>` (e.g. `playlunky/nightly`). Set it once:

   ```bash
   setx SPELUNKY2RL_PLAYLUNKY_DIR "C:\Users\You\AppData\Local\spelunky.fyi\modlunky2\playlunky\nightly"
   ```

   ![modlunky2 configuration](modlunky2config.png)

3. Install the package:

   ```bash
   git clone https://github.com/vicbentu/spelunky2RL.git
   cd spelunky2RL
   pip install .
   ```

On start, SpelunkyRL copies its mod into `Mods/Packs/spelunky2rl`, makes it the only mod in
`load_order.txt`, and sets `overlunky.ini` to autorun it (`autorun_scripts`, `script_dir`,
`enable_unsafe_scripts`).

## Your First Environment

Here's a minimal example to verify everything is working:

```python
from spelunky2rl.envs.dummy_environment import SpelunkyEnv

# Uses SPELUNKY2RL_GAME_DIR; or SpelunkyEnv(game_dir="/path/to/Spelunky 2")
env = SpelunkyEnv()

# Reset the environment
obs, info = env.reset()

# Take 100 random steps
for _ in range(100):
    action = env.action_space.sample()
    obs, reward, done, truncated, info = env.step(action)

    if done or truncated:
        obs, info = env.reset()

# Clean up
env.close()
```

## Environment Configuration

The `SpelunkyRLEngine` (base class for all environments) accepts several configuration parameters:

### Basic Parameters

```python
env = SpelunkyEnv(
    game_dir="/path/to/Spelunky 2",   # Optional: folder with Spel2.exe (default: $SPELUNKY2RL_GAME_DIR)
    frames_per_step=6,                # Optional: Game frames per RL step (default: 6)
    render_enabled=False,             # Optional: Enable render() method (default: False)
    launcher="auto",                  # Optional: "docker" (Linux default), "wine", "windows" (Windows default)
    renderer="auto",                  # Optional, Linux: "gpu", "cpu" or "auto" (GPU if Docker can use one)
    launcher_options=None,            # Optional: e.g. {"image": "..."} for Docker
    console=False,                    # Optional, Windows: Show Playlunky console (default: False)
    step_timeout=60.0,                # Optional: Max seconds to wait for the game each step
    startup_timeout=180.0,            # Optional: Max seconds for the game to start and connect
    max_launch_attempts=3,            # Optional: Relaunches if the game dies before connecting
)
```

If the game stops answering, `reset()`/`step()` raise `TimeoutError` instead of hanging.
`close()` can be called any number of times; it also runs automatically at interpreter exit.

### Reset Options

You can configure game settings via `reset()` or by passing them to `__init__()` as kwargs:

```python
# Option 1: Configure at initialization
env = SpelunkyEnv(
    hp=8,           # Start with 8 HP
    bombs=10,       # Start with 10 bombs
    world=2,        # Start in world 2
)

# Option 2: Configure at reset
obs, info = env.reset(
    seed=42,        # Set random seed
    hp=4,           # Start with 4 HP
    god_mode=True,  # Enable invulnerability
)
```

### Available Reset Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `seed` | int | Random | Random seed for level generation |
| `speedup` | bool | False | Allow game to run faster than 60 FPS |
| `state_updates` | int | 0 | Extra logic frames simulated per rendered frame when `speedup` (50-200 typical) |
| `manual_control` | bool | False | Enable keyboard control (useful for testing) |
| `god_mode` | bool | False | Player invulnerability |
| `hp` | int | 4 | Starting health |
| `bombs` | int | 4 | Starting bombs |
| `ropes` | int | 4 | Starting ropes |
| `gold` | int | 0 | Starting gold |
| `world` | int | 1 | Starting world (1-16, see [THEME](https://spelunky-fyi.github.io/overlunky/#THEME)) |
| `level` | int | 1 | Starting level within world |
| `ent_types_to_destroy` | list | [] | Entity type IDs to remove at level start |
| `theme` | int | None | Overlunky THEME id; None = the usual theme for `world`/`level` |
| `time_ghost` | bool | True | The ghost that appears after 3 minutes; it slows the game ~8x, disable for long episodes |
| `audio` | bool | False | Game audio |

## Performance Optimization

For training, you'll want to maximize speed:

```python
env = SpelunkyEnv(
    speedup=True,           # Run faster than real-time
    state_updates=200,      # Extra logic frames per rendered frame
    render_enabled=False,   # Don't capture frames

    # Training settings
    frames_per_step=6,      # Balance between reactivity and speed
)
```

**Note**: with `render_enabled=False` the game also skips drawing the level. Above `state_updates≈50`
the game is no longer the bottleneck (about 1,700 steps/s per instance with `frames_per_step=6`
measured on a Ryzen 9 7900X); the rest is the per-step exchange with Python. Do not use
`state_updates` when `render_enabled=True`: the frames you capture would skip most of the action.

## Manual Control (Testing)

To test your environment with keyboard controls:

```python
env = SpelunkyEnv(
    manual_control=True,    # Enable keyboard input
    god_mode=True,          # Useful for testing
    console=True,           # Show console for debugging
)

obs, info = env.reset()

# Game loop - keyboard controls are active
while True:
    # Action doesn't matter in manual_control mode
    obs, reward, done, truncated, info = env.step(env.action_space.sample())

    if done or truncated:
        obs, info = env.reset()
```

Controls:
- Arrow keys: Movement
- Z: Jump
- X: Whip/Attack
- C: Bomb
- V: Rope
- Shift: Run
- Up Arrow (at door): Enter door

See `examples/manual_control.py` for a complete example.

## Example Scripts

SpelunkyRL includes several example scripts in `examples/`:

- **`manual_control.py`** - Test environment with keyboard controls
- **`train_get_to_exit.py`** - Complete training example with RecurrentPPO
- **`evaluate_model.py`** - Evaluate a trained model
- **`record_video.py`** - Record video of agent gameplay

## Logging

SpelunkyRL can log game state information for debugging:

```python
env = SpelunkyEnv(
    log_file="game_log.txt",        # Where to save logs
    log_info=["all", "map_info"],   # What to log
)
```

Available log options:
- `"all"` - Full JSON gamestate with timestamp
- `"map_info"` - Formatted 11x21 terrain grid
- `"entity_count"` - Count of each entity type visible

## Next Steps

- **[Environments Guide](environments.md)** - Learn about available environments and create your own
- **[Architecture Guide](architecture.md)** - Understand how SpelunkyRL works internally
- **Example Scripts** - Check `examples/` for training and evaluation examples

## Troubleshooting

**Environment won't start:**
- Run `spelunky2rl doctor`
- The error message ends with the launcher's recent output (the container's, on Linux)
- Windows: check `SPELUNKY2RL_PLAYLUNKY_DIR` and that Overlunky is installed in the game folder

**Game is too slow:**
- Set `speedup=True`
- Increase `state_updates` (start with 100, increase gradually)
- Decrease `frames_per_step` (but this affects agent reactivity)

**Slow episodes after 3 minutes of game time:**
- That is the ghost; pass `time_ghost=False`

**Import errors:**
- Make sure you've installed the package: `pip install .`
- Check that your virtual environment is activated
- Verify all dependencies installed correctly
