import win32gui
import win32process
import win32api
import win32con

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

def press_ctrlf4(hwnd: int) -> None:
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(win32con.VK_F4, 0, 0, 0)
    win32api.keybd_event(win32con.VK_F4, 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
