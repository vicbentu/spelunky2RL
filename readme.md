# SpelunkyRL

SpelunkyRL is a Reinforcement Learning environment for Spelunky 2, providing a standard Gymnasium interface with predefined tasks and extensive customization options.

**Built on the excellent work by the spelunky-fyi community:**
- **[overlunky](https://github.com/spelunky-fyi/overlunky)** - Lua API for game state access and manipulation
- **[Playlunky](https://github.com/spelunky-fyi/Playlunky)** - Mod loading and script injection
- **[modlunky2](https://github.com/spelunky-fyi/modlunky2)** - Mod management and installation tools

## Features

- **Gymnasium Interface** - Standard RL environment API compatible with Stable-Baselines3 and other frameworks
- **Pre-built Environments** - Ready-to-use tasks (navigation, gold collection, combat)
- **Custom Environments** - Flexible system for creating your own tasks
- **High Performance** - Optimized for fast training with parallel environments
- **Complete Control** - Access to game state, entities, and full action space

## Quick Start

### Installation

1. Install [modlunky2](https://github.com/spelunky-fyi/modlunky2) and set up a modding copy of Spelunky 2
2. Clone this repo into `Spelunky 2\Mods\Packs\`
3. Install the package:

```bash
pip install .
```

### Basic Usage

```python
from spelunky2rl.envs.get_to_exit import SpelunkyEnv

env = SpelunkyEnv(
    spelunky_dir=r"C:\Path\To\Spelunky 2",
    playlunky_dir=r"C:\Path\To\playlunky\nightly"
)

obs, info = env.reset()
for _ in range(1000):
    action = env.action_space.sample()
    obs, reward, done, truncated, info = env.step(action)
    if done or truncated:
        obs, info = env.reset()

env.close()
```

## Available Environments

- **`dummy_environment`** - Minimal test environment
- **`get_to_exit`** - Navigate to the level exit as quickly as possible
- **`gold_grabber`** - Collect as much gold as possible within time limit
- **`enemy_killer`** - Combat-focused task to eliminate enemies

## Documentation

- **[Getting Started](docs/getting-started.md)** - Installation, configuration, and first steps
- **[Environments Guide](docs/environments.md)** - Creating and customizing environments
- **[Architecture Guide](docs/architecture.md)** - Technical details and internal workings

## Examples

Check `examples/` for complete examples:

- **`manual_control.py`** - Test environment with keyboard controls
- **`train_get_to_exit.py`** - Train an agent with RecurrentPPO
- **`evaluate_model.py`** - Evaluate trained models
- **`record_video.py`** - Record videos of agent gameplay

## 🔮 Future Work

- [ ] **Implement more tasks**: specially, long-term planning tasks that require extended sequences of actions and strategic decision-making.

- [ ] **Multi-agent scenarios**: both cooperative and competitive dynamics between multiple agents.

- [ ] **Dockerization**: streamlining the setup process and improving performance for broader accessibility.

- [ ] **Performance optimization**

- [ ] **Add customization options**: expanding the configuration possibilities.

- [ ] ...

## 🙏 Credits & Acknowledgments

This project would not be possible without the incredible work of the spelunky-fyi community:

- **[overlunky](https://github.com/spelunky-fyi/overlunky)** - The foundation of this project. Overlunky provides the comprehensive Lua API that enables game state access, entity manipulation, and real-time game control. All game interactions in SpelunkyRL are powered by overlunky's scripting capabilities.

- **[Playlunky](https://github.com/spelunky-fyi/Playlunky)** - Essential for mod loading and Lua script injection into Spelunky 2. Playlunky makes it possible to run our custom scripts alongside the game without modifying the original executable.

- **[modlunky2](https://github.com/spelunky-fyi/modlunky2)** - Provides the mod management infrastructure and tools that make setting up and running SpelunkyRL straightforward.

Special thanks to the entire spelunky-fyi community for maintaining these excellent tools and fostering the Spelunky modding ecosystem.
