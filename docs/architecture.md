# Architecture Guide

This guide explains how SpelunkyRL works internally - the communication protocol, process management, and technical implementation details.

## Table of Contents

- [System Overview](#system-overview)
- [Component Architecture](#component-architecture)
- [Communication Protocol](#communication-protocol)
- [Lifecycle Management](#lifecycle-management)
- [Data Flow](#data-flow)
- [Performance Considerations](#performance-considerations)

## System Overview

SpelunkyRL bridges Python-based RL frameworks with Spelunky 2 through a multi-layer architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                     Python RL Agent                          │
│              (Stable-Baselines3, etc.)                      │
└──────────────────────┬──────────────────────────────────────┘
                       │ Gymnasium Interface
                       │ (reset, step, close)
┌──────────────────────▼──────────────────────────────────────┐
│                SpelunkyRLEngine                              │
│  - Socket communication                                      │
│  - Process management                                        │
│  - Frame grabbing                                            │
│  - Observation/reward processing                             │
└──────────────────────┬──────────────────────────────────────┘
                       │ Socket (JSON over TCP)
┌──────────────────────▼──────────────────────────────────────┐
│                  Lua Script (in Spelunky 2)                  │
│                (via overlunky API)                           │
│  - Game state extraction                                     │
│  - Input injection                                           │
│  - Entity manipulation                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ overlunky API
┌──────────────────────▼──────────────────────────────────────┐
│               Spelunky 2 Game Engine                         │
└──────────────────────────────────────────────────────────────┘
```

**Key components**:

1. **Python Layer** (`SpelunkyRLEngine`)
   - Implements Gymnasium interface
   - Manages game process lifecycle
   - Handles socket communication
   - Processes observations and rewards

2. **Lua Layer** (injected scripts)
   - Extracts game state via overlunky API
   - Receives and executes actions
   - Sends data back to Python

3. **Game Layer** (Spelunky 2)
   - Runs the actual game
   - Modified by Lua scripts in real-time

## Component Architecture

### SpelunkyRLEngine (core.py)

The base class that all environments inherit from. Located in `src/spelunky2rl/engine/core.py`.

#### Key Responsibilities

1. **Process Management**
   - Launch Playlunky and Spelunky 2
   - Monitor game process health
   - Clean shutdown on close

2. **Socket Communication**
   - Create server socket
   - Accept connection from Lua script
   - Send/receive JSON messages

3. **State Management**
   - Track current and previous gamestate
   - Maintain episode state
   - Handle reset logic

4. **Gymnasium Interface**
   - Implement `reset()`, `step()`, `close()`, `render()`
   - Delegate to subclass methods for custom logic

#### Initialization Flow

```python
def __init__(self, spelunky_dir, playlunky_dir, **kwargs):
    # 1. Store configuration
    self.spelunky_dir = spelunky_dir
    self.playlunky_dir = playlunky_dir
    self.reset_options = kwargs

    # 2. Launch game and establish connection
    self._game_init()
```

The `_game_init()` method:

```python
def _game_init(self):
    # 1. Create load_order.txt (tells Playlunky to load the spelunky2rl pack)
    # 2. Create server socket on random port
    # 3. Set environment variable with port number
    # 4. Launch playlunky_launcher.exe
    # 5. Wait for Lua script to connect
    # 6. Find Spel2.exe process
    # 7. Get window handle for frame grabbing
    # 8. Register cleanup on exit
```

**Socket setup**:
```python
self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
self.server_socket.bind(('127.0.0.1', 0))  # Random available port
self.server_socket.listen(1)
port = self.server_socket.getsockname()[1]
os.environ["Spelunky_RL_Port"] = str(port)  # Lua script reads this
```

**Process discovery**:
```python
# Wait for playlunky to launch Spel2.exe
parent = psutil.Process(self.launcher_process.pid)
children = parent.children(recursive=True)
for child in children:
    if child.name().startswith("Spel2"):
        self.game_process = child
```

### Reset Mechanism

```python
def reset(self, seed=None, **kwargs):
    # 1. Call parent reset (handles RNG seeding)
    super().reset(seed=seed)

    # 2. Send reset command to Lua
    self._game_reset(seed=seed, **(self.reset_options | kwargs))

    # 3. Receive initial gamestate
    gamestate = self._receive_dict()

    # 4. Convert to observation
    observation = self.gamestate_to_observation(gamestate)

    # 5. Store for next step
    self.last_gamestate = gamestate

    return observation, {}
```

The `_game_reset()` method sends configuration to Lua:

```python
def _game_reset(self, seed, speedup, state_updates, hp, bombs, ...):
    self._send_dict({
        "command": "reset",
        "speedup": speedup,
        "state_updates": state_updates,
        "seed": seed,
        "ent_types_to_destroy": ent_types_to_destroy,
        "data_to_send": self.data_to_send,
        "manual_control": manual_control,
        "god_mode": god_mode,
        "hp": hp,
        "bombs": bombs,
        # ... more options
    })
```

### Step Mechanism

```python
def step(self, action):
    # 1. Convert action to default format (if custom action space)
    action = action.tolist() if not hasattr(self, 'action_to_input') \
             else self.action_to_input(action.tolist())

    # 2. Send action to Lua
    self._send_dict({
        "command": "step",
        "input": action,
        "frames": self.frames_per_step,
        "data_to_send": getattr(self, "data_to_send", [])
    })

    # 3. Receive updated gamestate
    gamestate = self._receive_dict()

    # 4. Calculate reward (delegated to subclass)
    reward, done, truncated, info = self.reward_function(
        gamestate, self.last_gamestate, action, info
    )

    # 5. Check automatic termination conditions
    done = done or (gamestate["basic_info"]["health"] <= 0 or
                    gamestate["basic_info"]["win"] == 1)

    # 6. Convert to observation
    observation = self.gamestate_to_observation(gamestate)

    # 7. Store for next step
    self.last_gamestate = gamestate

    return observation, reward, done, truncated, info
```

## Communication Protocol

### Message Format

All messages are JSON objects sent over TCP, terminated with `\n`:

**Python → Lua**:
```json
{
    "command": "step",
    "input": [1, 1, 0, 0, 0, 0, 1, 0],
    "frames": 6,
    "data_to_send": ["map_info", "dist_to_goal"]
}
```

**Lua → Python**:
```json
{
    "basic_info": {
        "time": 360,
        "health": 4,
        "bombs": 4,
        "ropes": 4,
        "money": 1500,
        "x_rest": 0.23,
        "y_rest": -0.45,
        "char_state": 12,
        "can_jump": true,
        "win": 0,
        "dead_enemies": 3
    },
    "map_info": [[...], [...], ...],
    "dist_to_goal": 42.5
}
```

### Send Implementation

```python
def _send_dict(self, payload):
    json_str = json.dumps(payload) + "\n"
    self.server.sendall(json_str.encode("utf-8"))
```

### Receive Implementation

```python
def _receive_dict(self):
    buffer = b""
    # Read until newline
    while not buffer.endswith(b"\n"):
        data = self.server.recv(1024)
        if not data:
            raise ConnectionError("Disconnected from Spelunky Lua script")
        buffer += data

    # Parse JSON
    json_str = buffer.decode("utf-8").strip()
    dict = json.loads(json_str)

    # Check for errors from Lua
    if "error" in dict:
        raise RuntimeError(dict["error"])

    return dict
```

### Command Types

**1. Reset Command**

```json
{
    "command": "reset",
    "seed": 12345,
    "speedup": true,
    "state_updates": 200,
    "ent_types_to_destroy": [219, 220, 221],
    "data_to_send": ["map_info", "dist_to_goal"],
    "manual_control": false,
    "god_mode": false,
    "hp": 4,
    "bombs": 4,
    "ropes": 4,
    "gold": 0,
    "world": 1,
    "level": 1
}
```

An optional `"theme"` (overlunky `THEME` id) overrides the default theme for `world`/`level`.

The Lua script responds with the initial gamestate.

**2. Step Command**

```json
{
    "command": "step",
    "input": [1, 1, 0, 1, 0, 0, 1, 0],
    "frames": 6,
    "data_to_send": ["map_info"]
}
```

The Lua script:
1. Applies the input for the specified number of frames
2. Extracts requested data
3. Responds with updated gamestate

**3. Close Command**

```json
{
    "command": "close"
}
```

Signals the Lua script to clean up (though process is also terminated).

## Lifecycle Management

### Startup Sequence

1. **Python creates socket server** on random port
2. **Python sets environment variable** `Spelunky_RL_Port` with port number
3. **Python launches Playlunky**
4. **Playlunky launches Spelunky 2** with mods
5. **Spelunky 2 loads the spelunky2rl mod pack** (via `load_order.txt`)
6. **Lua script reads port** from environment variable
7. **Lua script connects** to Python socket
8. **Python accepts connection** and proceeds

### Process Monitoring

The engine continuously monitors the game process:

```python
# In _game_init()
while True:
    try:
        self.server, addr = self.server_socket.accept()
        break  # Connection established
    except socket.timeout:
        pass

    # Check if game process is still alive
    if self.game_process is not None and self.game_process.is_running():
        continue
    else:
        # Relaunch if crashed
        if self.launcher_process.poll() is None:
            # Still launching...
            parent = psutil.Process(self.launcher_process.pid)
            children = parent.children(recursive=True)
            for child in children:
                if child.name().startswith("Spel2"):
                    self.game_process = child
```

### Shutdown Sequence

```python
def close(self):
    # 1. Send close command to Lua
    self._send_dict({"command": "close"})

    # 2. Terminate game process
    if hasattr(self, "game_process") and self.game_process is not None:
        try:
            self.game_process.terminate()
            self.game_process.wait(timeout=5)
        except Exception:
            pass  # Best-effort cleanup
```

The `atexit` handler ensures cleanup even on exceptions:

```python
atexit.register(self.close)
```

## Data Flow

### Observation Pipeline

```
Lua Gamestate → Python gamestate dict → gamestate_to_observation() → Gymnasium observation
```

**Example**:

```python
# Lua sends:
{
    "basic_info": {"char_state": 12, "can_jump": true, ...},
    "map_info": [[0, 0, 1, ...], ...]
}

# gamestate_to_observation() converts to:
{
    "char_state": np.int32(12),
    "can_jump": np.int32(1),
    "map_info": np.array([[0, 0, 1, ...], ...], dtype=np.int32)
}
```

### Action Pipeline

```
Agent action → action_to_input() → Default format → Lua → Spelunky 2 inputs
```

**Example**:

```python
# Agent outputs (custom action space):
[2, 1, 1]  # [right, no vertical, jump]

# action_to_input() converts to default format:
[2, 1, 1, 0, 0, 0, 1, 0]  # [right, no vertical, jump, no whip, no bomb, no rope, run, no door]

# Lua interprets:
# - Move right (2)
# - No vertical movement (1)
# - Jump (1)
# - Run (1)
```

### Reward Pipeline

```
Gamestate + Last Gamestate → reward_function() → (reward, done, truncated, info)
```

The reward function has access to:
- Current state
- Previous state (for computing deltas)
- Action taken
- Info dict to populate

## Performance Considerations

### Frame Skipping

`frames_per_step` controls how many game frames execute per RL step:

```python
env = SpelunkyEnv(frames_per_step=6)  # Default: 6 frames (~10 actions/sec at 60 FPS)
```

**Trade-off**:
- Lower values → More reactive but slower training
- Higher values → Faster training but less precise control

### State Updates (Speedup)

`state_updates` skips rendering and some game updates:

```python
env.reset(state_updates=200)
```

**How it works** (Lua side):
- For each RL step, run N "update only" frames
- These frames update physics but skip rendering
- Can increase speed 10-100x

**Limitations**:
- Maximum value depends on requested data
- Too high causes crashes (varies by environment)
- Cannot use with `render_enabled=True`

### Speedup Flag

`speedup=True` removes the 60 FPS cap:

```python
env.reset(speedup=True)
```

Allows the game to run as fast as the CPU permits.

### Data Optimization

Only request data you need in `data_to_send`:

```python
# Minimal (fastest)
data_to_send = ["map_info"]

# Medium
data_to_send = ["map_info", "dist_to_goal"]

# Maximum (slowest)
data_to_send = ["map_info", "dist_to_goal", "entity_info"]
```

**Cost**:
- `map_info`: Low (always computed)
- `dist_to_goal`: Medium (pathfinding calculation)
- `entity_info`: High (iterates all nearby entities)

### Render Mode

Frame grabbing has significant overhead:

```python
# Training (fast)
env = SpelunkyEnv(render_enabled=False)

# Evaluation/recording (slow)
env = SpelunkyEnv(render_enabled=True)
frame = env.render()  # Returns numpy array
```

**Implementation** (Windows-specific):

```python
# In _game_init()
if self.render_enabled:
    self.grabber = FrameGrabber(self.hwnd)  # Uses win32 APIs

# In render()
return self.grabber.get_frame()  # Screenshot via BitBlt
```

## Frame Grabber Implementation

Located in `src/spelunky2rl/engine/utils/frame_grabber.py`.

Uses Windows APIs to capture the game window:

```python
class FrameGrabber:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        # Get window DC, create compatible DC and bitmap

    def get_frame(self):
        # 1. BitBlt from window DC to memory DC
        # 2. Convert to numpy array
        # 3. Return RGB array
```

## Window Management

Located in `src/spelunky2rl/engine/utils/window_management.py`.

**Key functions**:

```python
def get_hwnd_for_pid(pid):
    """Find window handle for a process ID"""
    # Enumerate windows, match against PID

def press_ctrlf4(hwnd):
    """Send Ctrl+F4 to close Spelunky console window"""
    # Used when console=False
```

## Error Handling

### Lua Errors

Lua scripts can report errors:

```python
# Lua sends:
{"error": "Invalid world number: 99"}

# Python raises:
RuntimeError: Invalid world number: 99
```

### Connection Errors

```python
def _receive_dict(self):
    data = self.server.recv(1024)
    if not data:
        raise ConnectionError("Disconnected from Spelunky Lua script")
```

### Process Crashes

The engine attempts to detect and restart crashed processes in `_game_init()`, but this is best-effort.

## Logging

Optional logging for debugging:

```python
env = SpelunkyEnv(
    log_file="debug.txt",
    log_info=["all", "map_info", "entity_count"]
)
```

**Log implementation**:

```python
def log_step(self, gamestate):
    with open(self.log_file, "a") as f:
        if "all" in self.log_info:
            f.write(f"{timestamp} {str(gamestate)}\n")

        if "map_info" in self.log_info:
            for row in gamestate["map_info"]:
                formatted_row = " ".join(f"{cell:>3}" for cell in row)
                f.write(f"{formatted_row}\n")

        if "entity_count" in self.log_info:
            type_counts = Counter(id2name(e[4])["name"] for e in gamestate["entity_info"])
            f.write(f"Entities: {type_counts}\n")
```

## Dependencies

### Python Dependencies

From `pyproject.toml`:

- **gymnasium**: RL environment interface
- **stable-baselines3**: RL algorithms (optional, for training)
- **torch**: Deep learning (optional, for training)
- **numpy**: Numerical operations
- **pywin32**: Windows API access
- **psutil**: Process management

### System Dependencies

- **Spelunky 2**: The game
- **Playlunky**: Mod loader
- **modlunky2**: Mod management
- **overlunky**: Lua API (bundled with Playlunky)

## Next Steps

- **[Getting Started](getting-started.md)** - Installation and basic usage
- **[Environments Guide](environments.md)** - Create custom environments
- **Lua Scripts** - Located in `src/spelunky2rl/mod/lua/` (for advanced customization)
