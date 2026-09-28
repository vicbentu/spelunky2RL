import numpy as np


class FrameSource:
    """Where render() gets the game's pixels from."""

    def get_frame(self) -> np.ndarray:
        """Latest frame as an (H, W, 3) uint8 RGB array."""
        raise NotImplementedError

    def close(self) -> None:
        pass


class NullFrameSource(FrameSource):
    def __init__(self, reason: str):
        self.reason = reason

    def get_frame(self) -> np.ndarray:
        raise RuntimeError(self.reason)
