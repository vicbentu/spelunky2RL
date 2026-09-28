"""
Default Comprehensive Environment for SpelunkyRL

This environment provides a complete observation space with nearly all available game information,
making it suitable as a baseline for various tasks. It uses a variable-length sequence for entity
representation, preserving all entity information without spatial aggregation.

Observation Space:
- Terrain grid (11x21) of entity type IDs
- Variable-length list of entities with position, velocity, type, and facing direction
- Complete player state (character state, jump ability, velocity, facing)
- All resources (health, bombs, ropes, money)
- Items (holding, back item)
- All 18 powerups
- Level context (layer, world, level, theme, time)

Action Space:
- Full 8-action space: [Movement X, Movement Y, Jump, Whip, Bomb, Rope, Run, Door]

Reward Function (Placeholder):
- Simple goal-reaching reward
- Users should customize this for their specific task
"""

import numpy as np
import gymnasium as gym
from gymnasium.spaces import Dict, Box, Discrete, Sequence, Tuple

from spelunky2rl import SpelunkyRLEngine


class SpelunkyEnv(SpelunkyRLEngine):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ################## ENV CHARACTERISTICS ##################

    observation_space = Dict({
        # Terrain: 11x21 grid centered on player
        # Each cell contains the entity type ID of floor/wall tiles
        # Range: 0-916 (see overlunky ENT_TYPE enum)
        'map_info': Box(low=0, high=916, shape=(11, 21), dtype=np.int32),

        # Entities: Variable-length list of all nearby entities
        # Each entity tuple contains:
        #   - dx: relative x position from player (-10 to +10)
        #   - dy: relative y position from player (-5 to +5)
        #   - vx: velocity in x direction
        #   - vy: velocity in y direction
        #   - entity_type: entity type ID (0-915)
        #   - face_left: whether entity is facing left (0=right, 1=left)
        'entities': Sequence(
            Tuple((
                Box(low=-10, high=10, shape=(1,), dtype=np.float32),           # dx
                Box(low=-5, high=5, shape=(1,), dtype=np.float32),             # dy
                Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),   # vx
                Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),   # vy
                Box(low=0, high=915, shape=(1,), dtype=np.int32),              # entity_type
                Discrete(2),                                                   # face_left
            ))
        ),

        # Character state: Current animation/action state (0-22)
        # States include: standing, walking, jumping, falling, climbing, etc.
        # See overlunky CHAR_STATE enum for full list
        'char_state': Discrete(23),

        # Can jump: Whether the character can currently jump (0=no, 1=yes)
        # False when in air, on rope, etc.
        'can_jump': Discrete(2),

        # Velocity: Current player velocity [vx, vy]
        'velocity': Box(low=-np.inf, high=np.inf, shape=(2,), dtype=np.float32),

        # Facing left: Whether player is facing left (0=right, 1=left)
        # Important for direction (attacking, using items, etc)
        'facing_left': Discrete(2),

        # Health: Current health (typically 1-99, 4 starting health)
        'health': Discrete(100),

        # Bombs: Number of bombs in inventory (0-99)
        'bombs': Discrete(100),

        # Ropes: Number of ropes in inventory (0-99)
        'ropes': Discrete(100),

        # Money: Total money collected (in dollars, not gold value)
        'money': Box(low=0, high=999999, shape=(1,), dtype=np.int32),

        # Holding item: Type ID of item currently held (0 if none)
        'holding_item': Box(low=0, high=915, shape=(1,), dtype=np.int32),

        # Back item: Type ID of item on back/worn (0 if none)
        # Examples: jetpack, telepack, hoverpack, cape, etc.
        'back_item': Box(low=0, high=915, shape=(1,), dtype=np.int32),

        # Powerups: Binary array of 18 powerup states (0=don't have, 1=have)
        # Powerups include: climbing gloves, spike shoes, spring shoes, compass,
        # paste, spectacles, kapala, udjat eye, crown, eggplant crown, etc.
        'powerups': Box(low=0, high=1, shape=(18,), dtype=np.int32),

        # Layer: Current layer (0=FRONT, 1=BACK)
        'layer': Discrete(2),

        # World: Current world number (1-16)
        # Different worlds have different themes and mechanics
        'world': Discrete(17),

        # Level: Current level within world (typically 1-4)
        'level': Discrete(5),

        # Theme: Current theme ID (determines tile sets, enemies, etc.)
        # See overlunky THEME enum
        'theme': Discrete(20),

        # Time: Elapsed time in level (in frames, 60 frames = 1 second)
        'time': Box(low=0, high=999999, shape=(1,), dtype=np.int32),
    })

    # Full action space (default from SpelunkyRLEngine)
    # [Movement X, Movement Y, Jump, Whip, Bomb, Rope, Run, Door]
    # Each dimension: [0-2, 0-2, 0-1, 0-1, 0-1, 0-1, 0-1, 0-1]
    action_space = gym.spaces.MultiDiscrete([
        3,  # Movement X: 0=left, 1=nothing, 2=right
        3,  # Movement Y: 0=down, 1=nothing, 2=up
        2,  # Jump: 0=no jump, 1=jump
        2,  # Whip: 0=no whip, 1=whip
        2,  # Bomb: 0=no bomb, 1=bomb
        2,  # Rope: 0=no rope, 1=rope
        2,  # Run: 0=walk, 1=run
        2,  # Door: 0=no door action, 1=use door
    ])

    # Reset options: Minimal destruction (keep level mostly intact)
    # Users can override this when creating the environment
    reset_options = {
        "ent_types_to_destroy": []  # Don't destroy anything by default
    }

    # Data to request from Lua script
    data_to_send = [
        "map_info",      # Terrain grid
        "entity_info",   # Entity details
        "dist_to_goal"   # Distance to exit (for reward function)
    ]


    def reward_function(self, gamestate, last_gamestate, action, info):
        """
        Placeholder reward function - USERS SHOULD CUSTOMIZE THIS

        Default behavior:
        - Small step penalty to encourage efficiency
        - Large reward for reaching the exit
        - Time limit truncation

        Args:
            gamestate: Current game state
            last_gamestate: Previous game state
            action: Action taken
            info: Info dict to populate

        Returns:
            (reward, done, truncated, info)
        """
        truncated = False
        done = False
        reward_val = -0.01  # Small step penalty

        # Time limit: 90 seconds
        if gamestate["basic_info"]["time"] >= 60 * 90:
            truncated = True

        # Success: Reached exit
        if gamestate.get("dist_to_goal", float("inf")) <= 1:
            done = True
            reward_val += 10.0
            info["success"] = True
            info["time"] = gamestate["basic_info"]["time"]

        return float(reward_val), done, truncated, info


    def gamestate_to_observation(self, gamestate):
        """
        Convert raw gamestate from Lua to observation space format.

        Args:
            gamestate: Raw game state dict from Lua script

        Returns:
            observation: Dict matching observation_space definition
        """
        observation = {}

        # Terrain grid
        observation["map_info"] = np.array(gamestate["map_info"], dtype=np.int32)

        # Entity list (variable length)
        # Each entity in gamestate["entity_info"] is: [dx, dy, vx, vy, type, face_left, holding_type]
        observation["entities"] = [
            (
                np.array([ent[0]], dtype=np.float32),  # dx
                np.array([ent[1]], dtype=np.float32),  # dy
                np.array([ent[2]], dtype=np.float32),  # vx
                np.array([ent[3]], dtype=np.float32),  # vy
                np.array([ent[4]], dtype=np.int32),    # entity_type
                int(ent[5]),                            # face_left
            )
            for ent in gamestate["entity_info"]
        ]

        # Character state (clamp to valid range)
        char_state_raw = gamestate["basic_info"]["char_state"]
        observation["char_state"] = np.int32(np.clip(char_state_raw, 0, 22))

        # Can jump
        observation["can_jump"] = np.int32(int(gamestate["basic_info"]["can_jump"]))

        # Velocity
        observation["velocity"] = np.array([
            gamestate["basic_info"]["vel_x"],
            gamestate["basic_info"]["vel_y"]
        ], dtype=np.float32)

        # Facing direction
        observation["facing_left"] = np.int32(int(gamestate["basic_info"]["face_left"]))

        # Resources
        observation["health"] = np.int32(np.clip(gamestate["basic_info"]["health"], 0, 99))
        observation["bombs"] = np.int32(np.clip(gamestate["basic_info"]["bombs"], 0, 99))
        observation["ropes"] = np.int32(np.clip(gamestate["basic_info"]["ropes"], 0, 99))
        observation["money"] = np.array([gamestate["basic_info"]["money"]], dtype=np.int32)

        # Items
        observation["holding_item"] = np.array([gamestate["basic_info"]["holding_type_player"]], dtype=np.int32)
        observation["back_item"] = np.array([gamestate["basic_info"]["back_item"]], dtype=np.int32)

        # Powerups (18 total)
        observation["powerups"] = np.array(gamestate["basic_info"]["powerups"], dtype=np.int32)

        # Level context
        observation["layer"] = np.int32(np.clip(gamestate["basic_info"]["layer"], 0, 1))
        observation["world"] = np.int32(np.clip(gamestate["basic_info"]["world"], 1, 16))
        observation["level"] = np.int32(np.clip(gamestate["basic_info"]["level"], 1, 4))
        observation["theme"] = np.int32(np.clip(gamestate["basic_info"]["theme"], 0, 19))
        observation["time"] = np.array([gamestate["basic_info"]["time"]], dtype=np.int32)

        return observation
