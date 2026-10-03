"""
Enemy Killer Environment

A combat-focused task where the agent must kill as many enemies as possible.

Observation Space:
- Terrain grid (11x21) of entity type IDs
- Variable-length list of nearby entities with position, velocity, type, facing direction, and held item
- Character state (current animation/action state)
- Can jump (whether the player can currently jump)

Action Space:
- 4-action space: [Movement X, Movement Y, Jump, Attack]

Reward Function:
- Reward of 0.5 for each enemy killed
- Truncation after 90 seconds

Notes:
- Destroys shopkeepers and traps at level start
- Keeps enemies intact for combat
- Entity information includes enemies filtered to types 219-342
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
        'map_info': Box(low=0, high=916, shape=(1, 11, 21), dtype=np.int32),
        "char_state": Discrete(23),
        "can_jump"  : Discrete(2),
        "enemies": Sequence(
            Tuple((
                Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),
                Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),
                Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),
                Box(low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32),
                Box(low=0, high=915, shape=(1,), dtype=np.float32),
                Discrete(2),
                Box(low=0, high=915, shape=(1,), dtype=np.float32)
            )),
        )
    })

    action_space: gym.spaces.MultiDiscrete = gym.spaces.MultiDiscrete([
        3, # Movement X
        3, # Movement Y
        2, # Jump
        2, # Attack
    ])


    reset_options = {
        "ent_types_to_destroy": [600,601] + list(range(899, 906))
    }

    data_to_send = [
        "map_info",
        "entity_info"
    ]


    def action_to_input(self, action):
        return action + [0,0,1,0]

    def reward_function(self, gamestate, last_gamestate, action, info):
        truncated = False
        done = False

        if gamestate["basic_info"]["time"] >= 60*90: # 90 seconds
            truncated = True

        reward_val = (gamestate["basic_info"]["dead_enemies"] - last_gamestate["basic_info"]["dead_enemies"])*0.5
        return float(reward_val), done, truncated, info

    def gamestate_to_observation(self, gamestate):
        observation = {}

        observation["map_info"] = np.array(gamestate["map_info"], dtype=np.int32)[np.newaxis]
        observation["char_state"] = np.int64(np.clip(gamestate["basic_info"]["char_state"], 0, 22))
        observation["can_jump"] = np.int64(int(gamestate["basic_info"]["can_jump"]))
        # Gymnasium's Sequence space only contains tuples
        observation["enemies"] = tuple(
            (
                np.array([ent[0]], dtype=np.float32),
                np.array([ent[1]], dtype=np.float32),
                np.array([ent[2]], dtype=np.float32),
                np.array([ent[3]], dtype=np.float32),
                np.array([ent[4]], dtype=np.float32),
                int(ent[5]),
                np.array([ent[6]], dtype=np.float32)
            )
            for ent in gamestate["entity_info"]
            if 219 <= ent[4] <= 342  # filter by type
        )

        return observation
