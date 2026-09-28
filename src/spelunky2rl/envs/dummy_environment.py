"""
Dummy Environment for Testing and Debugging

A minimal environment designed for manual control and testing purposes.

Observation Space:
- Single boolean: can_jump (always returns 1, minimal observation)

Action Space:
- 3-action simplified space: [Movement X, Movement Y, Jump]

Reward Function:
- Always returns 0 (no learning, only for testing)
- Truncates after 90 seconds

Reset Options:
- manual_control=True: Allows keyboard control of the game
- god_mode=True: Player is invulnerable
- No entities destroyed

Use Cases:
- Testing game mechanics manually
- Debugging game state
- Observing game behavior without RL
"""

import numpy as np
import gymnasium as gym
from gymnasium.spaces import Dict, Discrete

from spelunky2rl import SpelunkyRLEngine

class SpelunkyEnv(SpelunkyRLEngine):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ################## ENV CHARACTERISTICS ##################

    observation_space = Dict({
        "can_jump"  : Discrete(2)
    })

    action_space: gym.spaces.MultiDiscrete = gym.spaces.MultiDiscrete([
        3, # Movement X
        3, # Movement Y
        2, # Jump
    ])

    reset_options = {
        "ent_types_to_destroy": [],
        "manual_control": True,
        "god_mode": True,

    }

    data_to_send = []

    def action_to_input(self, action):
        return action + [0,0,0,1,0]

    def reward_function(self, gamestate, last_gamestate, action, info):
        truncated = False
        if gamestate["basic_info"]["time"] >= 60*90: # 90 seconds
            truncated = True

        return 0.0, False, truncated, info

    def gamestate_to_observation(self, gamestate):
        observation = {}
        observation["can_jump"] = np.int32(1)

        return observation
