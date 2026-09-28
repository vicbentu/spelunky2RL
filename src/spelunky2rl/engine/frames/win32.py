"""Windows-only: capture the game window with PrintWindow. Imported lazily by the Windows launcher."""

import ctypes
import threading

import numpy as np
import win32gui
import win32process
import win32ui

from .base import FrameSource


def get_hwnd_for_pid(pid: int) -> int:
        """
        Return the HWND of the first visible, enabled, top‑level window
        that belongs to the given PID. Raises RuntimeError if none found.
        """
        candidates: list[int] = []

        def _enum(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.IsWindowEnabled(hwnd):
                _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                if win_pid == pid:
                    candidates.append(hwnd)
            return True

        win32gui.EnumWindows(_enum, None)

        if not candidates:
            raise RuntimeError(f"No window found for PID {pid}")
        return candidates[0]


class FrameGrabber(threading.Thread):
    def __init__(self, hwnd):
        super().__init__(daemon=True)
        self.hwnd = hwnd

        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        self.w, self.h = right - left, bottom - top

        hdc_window = win32gui.GetWindowDC(hwnd)
        self.mfcDC  = win32ui.CreateDCFromHandle(hdc_window)
        self.saveDC = self.mfcDC.CreateCompatibleDC()
        self.bmp    = win32ui.CreateBitmap()
        self.bmp.CreateCompatibleBitmap(self.mfcDC, self.w, self.h)
        self.saveDC.SelectObject(self.bmp)

        self._buf  = (ctypes.c_char * (self.w * self.h * 4))()
        self.frame = np.empty((self.h, self.w, 3), dtype=np.uint8)
        self._stop_event = threading.Event()

        self.start()

    def run(self):
        gdi  = ctypes.windll.gdi32
        user = ctypes.windll.user32
        while not self._stop_event.is_set():
            user.PrintWindow(self.hwnd, self.saveDC.GetSafeHdc(), 2)
            gdi.GetBitmapBits(self.bmp.GetHandle(), len(self._buf),
                              ctypes.byref(self._buf))
            np.copyto(
                self.frame,
                np.frombuffer(self._buf, dtype=np.uint8)
                  .reshape(self.h, self.w, 4)[..., :3][:, :, ::-1])

    def stop(self):
        self._stop_event.set()

    def get_frame(self):
        return self.frame.copy()


class Win32FrameSource(FrameSource):
    def __init__(self, pid: int):
        self.hwnd = get_hwnd_for_pid(pid)
        self.grabber = FrameGrabber(self.hwnd)
        win32gui.SetWindowText(self.hwnd, f"R_{win32gui.GetWindowText(self.hwnd)}")

    def get_frame(self) -> np.ndarray:
        return self.grabber.get_frame()

    def close(self) -> None:
        self.grabber.stop()
