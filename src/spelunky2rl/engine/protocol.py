"""JSON-lines protocol between Python and the Lua mod (mod/lua/spelunky2rl/protocol.lua).

Python listens on 127.0.0.1 and the Lua mod connects. The mod first sends
``{"hello": {"protocol": N, "mod": "x.y.z"}}``; after that every message from Python
(reset, step, close) is answered by one game state, except close.
"""

import json
import socket
from typing import Any, Dict, Optional

from ..version import __version__

# Bump when a message changes shape; keep in sync with PROTOCOL_VERSION in mod/lua/spelunky2rl/protocol.lua
PROTOCOL_VERSION = 1


class ProtocolError(RuntimeError):
    """The game runs a mod that does not speak this package's protocol."""


class Connection:
    """One newline-delimited JSON stream over a connected socket."""

    def __init__(self, sock: socket.socket, timeout: Optional[float]):
        self.sock = sock
        self.timeout = timeout
        self._buffer = b""
        sock.settimeout(timeout)
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            # one small message each way per step: never wait to batch
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def send(self, payload: Dict[str, Any]) -> None:
        self.sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))

    def receive(self, timeout: Optional[float] = None) -> Dict[str, Any]:
        timeout = self.timeout if timeout is None else timeout
        self.sock.settimeout(timeout)
        try:
            while b"\n" not in self._buffer:
                try:
                    data = self.sock.recv(65536)
                except socket.timeout:
                    raise TimeoutError(f"No response from the Spelunky Lua script in {timeout} s") from None
                if not data:
                    raise ConnectionError("Disconnected from Spelunky Lua script")
                self._buffer += data
        finally:
            self.sock.settimeout(self.timeout)
        line, self._buffer = self._buffer.split(b"\n", 1)
        message = json.loads(line.decode("utf-8"))
        if "error" in message:
            raise RuntimeError(message["error"])
        return message

    def close(self) -> None:
        self.sock.close()


def check_hello(message: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the mod's first message and return its contents."""
    hello = message.get("hello")
    if not isinstance(hello, dict) or hello.get("protocol") != PROTOCOL_VERSION:
        got = hello.get("protocol") if isinstance(hello, dict) else None
        mod = hello.get("mod", "unknown") if isinstance(hello, dict) else "unknown"
        raise ProtocolError(
            f"The game runs spelunky2rl mod {mod} (protocol {got}), but this package "
            f"(spelunky2rl {__version__}) needs protocol {PROTOCOL_VERSION}. "
            f"Use the game image tagged {__version__} (spelunky2rl pull) or the mod from this package."
        )
    return hello
