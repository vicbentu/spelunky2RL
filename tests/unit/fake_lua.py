"""A stand-in for the Lua mod: speaks the JSON-lines protocol and answers with synthetic game states."""

import json
import socket
import threading

import numpy as np


def make_gamestate(rng, time=60, health=4, dist_to_goal=50, dead_enemies=0, money=0, win=0,
                   data_to_send=("map_info", "dist_to_goal", "entity_info")):
    """A game state with the shape and value ranges that the mod produces."""
    gamestate = {
        "basic_info": {
            "x": 20.0, "y": 100.0, "x_rest": 0.3, "y_rest": 0.05, "layer": 0,
            "health": health, "bombs": 4, "ropes": 4, "money": money,
            "vel_x": 0.0, "vel_y": -0.1, "face_left": bool(rng.integers(2)),
            "powerups": [0] * 18, "holding_type_player": 0, "back_item": 0,
            "char_state": int(rng.integers(0, 23)), "can_jump": bool(rng.integers(2)),
            "world": 1, "level": 1, "theme": 1, "time": time, "win": win,
            "dead_enemies": dead_enemies,
        },
    }
    if "map_info" in data_to_send:
        gamestate["map_info"] = rng.choice([0, 1, 4, 13, 15, 23, 114], size=(11, 21)).tolist()
    if "dist_to_goal" in data_to_send:
        gamestate["dist_to_goal"] = dist_to_goal
    if "entity_info" in data_to_send:
        gamestate["entity_info"] = [
            [float(rng.uniform(-10.5, 10.5)), float(rng.uniform(-5.5, 5.5)), 0.0, 0.0,
             int(entity_type), int(rng.integers(2)), 0]
            for entity_type in (220, 495, 600)
        ]
    return gamestate


class FakeLua(threading.Thread):
    """Client end of the engine socket. `respond(message, step_index)` returns the state to send,
    or None to stay silent. Every received message is kept in `messages`."""

    def __init__(self, sock: socket.socket, respond=None, seed=0, hello=None):
        super().__init__(daemon=True)
        self.sock = sock
        self.hello = hello
        self.rng = np.random.default_rng(seed)
        self.respond = respond or self.default_respond
        self.messages = []
        self.steps = 0
        self.start()

    def default_respond(self, message, steps):
        return make_gamestate(self.rng, time=60 + 6 * steps, data_to_send=message.get("data_to_send", []))

    def run(self):
        if self.hello is not None:
            self.sock.sendall((json.dumps(self.hello) + "\n").encode())
        reader = self.sock.makefile("rb")
        try:
            for line in reader:
                message = json.loads(line)
                self.messages.append(message)
                if message["command"] == "close":
                    break
                if message["command"] == "reset":
                    self.steps = 0
                else:
                    self.steps += 1
                reply = self.respond(message, self.steps)
                if reply is not None:
                    self.sock.sendall((json.dumps(reply) + "\n").encode())
        except OSError:
            pass
        finally:
            reader.close()
            self.sock.close()
