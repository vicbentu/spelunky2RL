"""
Get to Exit Environment

A goal-reaching task where the agent must navigate to the level exit as quickly as possible.

Observation Space:
- Terrain grid (11x21) of entity type IDs centered on the player
- Character state (current animation/action state)
- Can jump (whether the player can currently jump)

Action Space:
- 3-action simplified space: [Movement X, Movement Y, Jump]

Reward Function:
- Small step penalty (-0.01) to encourage efficiency
- Distance-based reward shaping (reward for getting closer to exit)
- Large bonus for reaching the exit
- Truncation after 90 seconds or 200 steps without improvement
"""

import numpy as np
import gymnasium as gym
from gymnasium.spaces import Dict, Box, Discrete

from spelunky2rl import SpelunkyRLEngine

class SpelunkyEnv(SpelunkyRLEngine):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    ################## ENV CHARACTERISTICS ##################

    observation_space = Dict({
        'map_info': Box(low=0, high=1, shape=(5, 11, 21), dtype=np.uint8),
        "char_state": Discrete(23),
        "can_jump"  : Discrete(2)
    })

    action_space: gym.spaces.MultiDiscrete = gym.spaces.MultiDiscrete([
        3, # Movement X
        3, # Movement Y
        2, # Jump
    ])

    reset_options = {
        "ent_types_to_destroy": [600,601] + list(range(219, 342)) + list(range(899, 906))
    }

    data_to_send = [
        "map_info",
        "dist_to_goal"
    ]


    def action_to_input(self, action):
        return action + [0,0,0,1,0]

    def reward_function(self, gamestate, last_gamestate, action, info):
        truncated = False
        done = False
        reward_val = -0.01  # small penalty for each step to encourage faster completion

        # Too much time
        if gamestate["basic_info"]["time"] >= 60*90: # 90 seconds
            truncated = True
            # reward_val -= 5

        # Level completed
        if gamestate["dist_to_goal"] == 0:
            done = True
            reward_val += (((60*90) - gamestate["basic_info"]["time"]) / (60*90))*5
            info["success"] = True
            info["time"] = gamestate["basic_info"]["time"]

        # No progress, clipping
        if gamestate["dist_to_goal"] < getattr(self, "min_dist_to_goal", float("inf")):
            self.min_dist_to_goal = gamestate["dist_to_goal"]
            self.no_improve_counter = 0
        else:
            self.no_improve_counter += 1
        if self.no_improve_counter >= 200:
            truncated = True
            reward_val -= 5

        # Penalize for the rest of steps
        if truncated:
            max_steps = (60*90) / self.frames_per_step
            timesteps = gamestate["basic_info"]["time"] / self.frames_per_step
            reward_val -= 0.01 * (max_steps - timesteps)
        if done or truncated:
            self.min_dist_to_goal = float("inf")

        # Reward getting close to the goal
        reward_val += (last_gamestate["dist_to_goal"] - gamestate["dist_to_goal"])*0.1

        return float(reward_val), done, truncated, info

    def gamestate_to_observation(self, gamestate):
        observation = {}
        map_info = np.array(gamestate["map_info"])

        m0 = (map_info == 0)                                 # empty space
        m1 = (15 <= map_info) & (map_info <= 21)             # stairs, etc
        m2 = (map_info == 23)                                # exit
        m3 = np.isin(map_info, (13, 16))                     # platform
        m4 = ~(m0 | m1 | m2 | m3)                            # else -> ground
        multi_hot = np.stack([m0, m1, m2, m3, m4]).astype(np.uint8)

        observation["map_info"] = multi_hot

        observation["char_state"] = np.int64(np.clip(gamestate["basic_info"]["char_state"], 0, 22))
        observation["can_jump"] = np.int64(int(gamestate["basic_info"]["can_jump"]))

        return observation
