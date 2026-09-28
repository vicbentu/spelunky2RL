import threading, ctypes
import win32gui, win32ui
import numpy as np

import ctypes
user=ctypes.windll.user32

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

        self.start()

    def run(self):
        gdi  = ctypes.windll.gdi32
        user = ctypes.windll.user32
        while True:
            user.PrintWindow(self.hwnd, self.saveDC.GetSafeHdc(), 2)
            gdi.GetBitmapBits(self.bmp.GetHandle(), len(self._buf),
                              ctypes.byref(self._buf))
            np.copyto(
                self.frame,
                np.frombuffer(self._buf, dtype=np.uint8)
                  .reshape(self.h, self.w, 4)[..., :3][:, :, ::-1])
            
            self.frame = self.frame.copy()

    def get_frame(self):
        return self.frame.copy()