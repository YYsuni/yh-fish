# -*- coding: utf-8 -*-
"""游戏窗口输入：键盘 PostMessage；鼠标分消息路径 `send_left_click` 与物理路径 `send_left_click_physical`（置前+SendInput）。"""

from __future__ import annotations

import sys
import time

VK_F = 0x46

# 键盘 Post WM_ACTIVATE 后停顿（秒）
KEYBOARD_ACTIVATE_DELAY_S = 0.01
# 鼠标 SendMessage 节奏（秒）：激活后停顿、相邻消息间隔、完整点击时按下保持（DOWN→UP 之间）
MOUSE_ACTIVATE_DELAY_S = 0.02
MOUSE_STEP_DELAY_S = 0.03
MOUSE_CLICK_HOLD_S = 0.2
# 点击前先悬停（消息路径用 TrackMouseEvent；物理路径用光标停留）
MOUSE_HOVER_DWELL_S = 0.45

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _INPUT_MOUSE = 0
    _MOUSEEVENTF_LEFTDOWN = 0x0002
    _MOUSEEVENTF_LEFTUP = 0x0004
    _HWND_TOP = 1
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _SWP_SHOWWINDOW = 0x0040

    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_ACTIVATE = 0x0006
    WA_ACTIVE = 1
    GA_ROOT = 2
    GA_ROOTOWNER = 3
    MAPVK_VK_TO_VSC = 0

    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    MK_LBUTTON = 0x0001

    TME_HOVER = 0x00000001
    HOVER_DEFAULT = 0xFFFFFFFF

    class _TRACKMOUSEEVENT(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("hwndTrack", wintypes.HWND),
            ("dwHoverTime", wintypes.DWORD),
        ]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetLastActivePopup.argtypes = [wintypes.HWND]
    _user32.GetLastActivePopup.restype = wintypes.HWND
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    _user32.MapVirtualKeyW.restype = wintypes.UINT
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.SendMessageW.restype = ctypes.c_ssize_t
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(_POINT)]
    _user32.ClientToScreen.restype = wintypes.BOOL
    _user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(_POINT)]
    _user32.ScreenToClient.restype = wintypes.BOOL
    _user32.GetCapture.argtypes = []
    _user32.GetCapture.restype = wintypes.HWND
    _user32.RealChildWindowFromPoint.argtypes = [wintypes.HWND, _POINT]
    _user32.RealChildWindowFromPoint.restype = wintypes.HWND
    _user32.TrackMouseEvent.argtypes = [ctypes.POINTER(_TRACKMOUSEEVENT)]
    _user32.TrackMouseEvent.restype = wintypes.BOOL
    _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _user32.SetCursorPos.restype = wintypes.BOOL
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        )

    class _INPUTUNION(ctypes.Union):
        _fields_ = (("mi", _MOUSEINPUT),)

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))

    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT

    _set_thread_dpi_ctx = getattr(_user32, "SetThreadDpiAwarenessContext", None)
    if _set_thread_dpi_ctx is not None:
        _set_thread_dpi_ctx.argtypes = [wintypes.HANDLE]
        _set_thread_dpi_ctx.restype = wintypes.HANDLE
    _DPI_AWARE_PER_MONITOR_V2 = -4

    def _MAKELPARAM(lo: int, hi: int) -> int:
        return int((hi & 0xFFFF) << 16 | (lo & 0xFFFF))

    def _hover_skip_and_seconds(hover_dwell_s: float | None) -> tuple[bool, float]:
        """显式 `hover_dwell_s<=0` 表示不要悬停段；否则返回 (False, 秒数)。"""
        if hover_dwell_s is not None and float(hover_dwell_s) <= 0:
            return True, 0.0
        sec = MOUSE_HOVER_DWELL_S if hover_dwell_s is None else max(0.0, float(hover_dwell_s))
        return False, sec

    def _get_active_hwnd(hwnd: int) -> int:
        """Maa MessageInput::get_active_hwnd：可见的最后活动弹出子窗，否则原 hwnd。"""
        if hwnd <= 0:
            return 0
        h = wintypes.HWND(hwnd)
        root = _user32.GetAncestor(h, GA_ROOTOWNER)
        if not root:
            return hwnd
        popup = _user32.GetLastActivePopup(root)
        if popup and int(popup) != hwnd and _user32.IsWindowVisible(popup):
            return int(popup)
        return hwnd

    def _same_root_hwnd(a: int, b: int) -> bool:
        """是否同一 GA_ROOT 顶层。"""
        if a <= 0 or b <= 0:
            return False
        ra = _user32.GetAncestor(wintypes.HWND(a), GA_ROOT)
        rb = _user32.GetAncestor(wintypes.HWND(b), GA_ROOT)
        return bool(ra and rb and int(ra) == int(rb))

    def _delivery_hwnd_lbutton_down(source_hwnd: int, cx: int, cy: int) -> int:
        """RealChildWindowFromPoint：客户区 (cx,cy) 最深子窗，无则 source。"""
        if source_hwnd <= 0:
            return 0
        ch = _user32.RealChildWindowFromPoint(wintypes.HWND(source_hwnd), _POINT(int(cx), int(cy)))
        if ch and _user32.IsWindow(ch) and int(ch) != int(source_hwnd):
            return int(ch)
        return int(source_hwnd)

    def _delivery_hwnd_lbutton_up(source_hwnd: int, cx: int, cy: int) -> int:
        """优先 GetCapture()（同根），否则同 _delivery_hwnd_lbutton_down。"""
        cap = _user32.GetCapture()
        c = int(cap) if cap else 0
        if c and _user32.IsWindow(wintypes.HWND(c)) and _same_root_hwnd(c, source_hwnd):
            return c
        return _delivery_hwnd_lbutton_down(source_hwnd, cx, cy)

    def _ensure_foreground_and_topmost(hwnd: int) -> None:
        """Maa InputUtils::ensure_foreground_and_topmost。"""
        if hwnd <= 0 or not _user32.IsWindow(wintypes.HWND(hwnd)):
            return
        h = wintypes.HWND(hwnd)
        if h == _user32.GetForegroundWindow():
            return
        f = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW
        _user32.SetWindowPos(h, wintypes.HWND(_HWND_TOP), 0, 0, 0, 0, f)
        time.sleep(0.005)
        _user32.SetForegroundWindow(h)
        time.sleep(0.01)
        if h != _user32.GetForegroundWindow():
            _user32.SetWindowPos(h, wintypes.HWND(_HWND_TOP), 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE)
            time.sleep(0.005)

    def _send_activate_post(target: int) -> None:
        """键盘路径：Post WM_ACTIVATE + 短延迟。"""
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return
        _user32.PostMessageW(wintypes.HWND(target), WM_ACTIVATE, wintypes.WPARAM(WA_ACTIVE), wintypes.LPARAM(0))
        time.sleep(KEYBOARD_ACTIVATE_DELAY_S)

    def _send_activate_sync(target: int) -> None:
        """鼠标：Send WM_ACTIVATE + MOUSE_ACTIVATE_DELAY_S。"""
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return
        _user32.SendMessageW(wintypes.HWND(target), WM_ACTIVATE, wintypes.WPARAM(WA_ACTIVE), wintypes.LPARAM(0))
        time.sleep(MOUSE_ACTIVATE_DELAY_S)

    def _make_mouse_lparam(source_hwnd: int, target_hwnd: int, cx: int, cy: int) -> int:
        """source 客户区坐标 → target 客户区 LPARAM（Maa make_mouse_lparam）。"""
        if source_hwnd == target_hwnd:
            return _MAKELPARAM(cx, cy)
        pt = _POINT(cx, cy)
        if not _user32.ClientToScreen(wintypes.HWND(source_hwnd), ctypes.byref(pt)):
            return _MAKELPARAM(cx, cy)
        if not _user32.ScreenToClient(wintypes.HWND(target_hwnd), ctypes.byref(pt)):
            return _MAKELPARAM(cx, cy)
        return _MAKELPARAM(int(pt.x), int(pt.y))

    def _make_keydown_lparam(vk: int) -> int:
        sc = int(_user32.MapVirtualKeyW(vk & 0xFF, MAPVK_VK_TO_VSC)) & 0xFF
        return 1 | (sc << 16)

    def _make_keyup_lparam(vk: int) -> int:
        sc = int(_user32.MapVirtualKeyW(vk & 0xFF, MAPVK_VK_TO_VSC)) & 0xFF
        return 1 | (sc << 16) | (1 << 30) | (1 << 31)

    def _post_key(target: int, vk: int, *, key_up: bool) -> bool:
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return False
        vk_i = int(vk) & 0xFF
        _send_activate_post(target)
        msg = WM_KEYUP if key_up else WM_KEYDOWN
        lp = _make_keyup_lparam(vk_i) if key_up else _make_keydown_lparam(vk_i)
        return bool(_user32.PostMessageW(wintypes.HWND(target), msg, wintypes.WPARAM(vk_i), wintypes.LPARAM(lp)))

    def _send_mouse_sync(target: int, source_hwnd: int, msg: int, wparam: int, cx: int, cy: int) -> bool:
        """SendMessageW 鼠标消息（同步顺序）。"""
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return False
        lp = _make_mouse_lparam(source_hwnd, target, cx, cy)
        _user32.SendMessageW(wintypes.HWND(target), msg, wintypes.WPARAM(wparam), wintypes.LPARAM(lp))
        return True

    def send_key_tap(hwnd: int, vk: int) -> bool:
        t = _get_active_hwnd(hwnd)
        return _post_key(t, vk, key_up=False) and _post_key(t, vk, key_up=True)

    def send_key_down(hwnd: int, vk: int) -> bool:
        return _post_key(_get_active_hwnd(hwnd), vk, key_up=False)

    def send_key_up(hwnd: int, vk: int) -> bool:
        return _post_key(_get_active_hwnd(hwnd), vk, key_up=True)

    def send_hover_at(hwnd: int, client_x: int, client_y: int, *, dwell_s: float | None = None) -> bool:
        """WM_MOUSEMOVE(0) → TrackMouseEvent(TME_HOVER) → sleep(dwell) → WM_MOUSEMOVE(0)。"""
        src = int(hwnd)
        if src <= 0 or not _user32.IsWindow(wintypes.HWND(src)):
            return False
        cx, cy = int(client_x), int(client_y)
        delivery = _delivery_hwnd_lbutton_down(src, cx, cy)
        if delivery <= 0:
            return False
        _send_activate_sync(delivery)
        if not _send_mouse_sync(delivery, src, WM_MOUSEMOVE, 0, cx, cy):
            return False
        time.sleep(MOUSE_STEP_DELAY_S)
        tme = _TRACKMOUSEEVENT()
        tme.cbSize = ctypes.sizeof(_TRACKMOUSEEVENT)
        tme.dwFlags = TME_HOVER
        tme.hwndTrack = wintypes.HWND(delivery)
        tme.dwHoverTime = HOVER_DEFAULT
        _user32.TrackMouseEvent(ctypes.byref(tme))
        _, dwell_sec = _hover_skip_and_seconds(dwell_s)
        time.sleep(dwell_sec)
        _send_mouse_sync(delivery, src, WM_MOUSEMOVE, 0, cx, cy)
        return True

    def send_left_down(hwnd: int, client_x: int, client_y: int) -> bool:
        """SendMessage：MOVE(MK_LBUTTON) → LBUTTONDOWN。"""
        src = int(hwnd)
        if src <= 0 or not _user32.IsWindow(wintypes.HWND(src)):
            return False
        cx, cy = int(client_x), int(client_y)
        delivery = _delivery_hwnd_lbutton_down(src, cx, cy)
        if delivery <= 0:
            return False
        _send_activate_sync(delivery)
        if not _send_mouse_sync(delivery, src, WM_MOUSEMOVE, MK_LBUTTON, cx, cy):
            return False
        time.sleep(MOUSE_STEP_DELAY_S)
        return _send_mouse_sync(delivery, src, WM_LBUTTONDOWN, MK_LBUTTON, cx, cy)

    def send_left_up(hwnd: int, client_x: int, client_y: int) -> bool:
        """SendMessage：MOVE(0) → LBUTTONUP（投递 HWND 见 _delivery_hwnd_lbutton_up）。"""
        src = int(hwnd)
        if src <= 0 or not _user32.IsWindow(wintypes.HWND(src)):
            return False
        cx, cy = int(client_x), int(client_y)
        delivery = _delivery_hwnd_lbutton_up(src, cx, cy)
        if delivery <= 0:
            return False
        _send_activate_sync(delivery)
        if not _send_mouse_sync(delivery, src, WM_MOUSEMOVE, 0, cx, cy):
            return False
        time.sleep(MOUSE_STEP_DELAY_S)
        return _send_mouse_sync(delivery, src, WM_LBUTTONUP, 0, cx, cy)

    def send_left_click(
        hwnd: int,
        client_x: int,
        client_y: int,
        *,
        hold_s: float | None = None,
        hover_dwell_s: float | None = None,
    ) -> bool:
        """消息路径：可选 `send_hover_at` 后 down→hold→up。`hover_dwell_s=0` 跳过悬停段。"""
        skip_h, hd = _hover_skip_and_seconds(hover_dwell_s)
        if not skip_h and not send_hover_at(hwnd, client_x, client_y, dwell_s=hd):
            return False
        if not send_left_down(hwnd, client_x, client_y):
            return False
        hold = MOUSE_CLICK_HOLD_S if hold_s is None else max(0.0, float(hold_s))
        time.sleep(hold)
        return send_left_up(hwnd, client_x, client_y)

    def send_left_click_physical(
        hwnd: int,
        client_x: int,
        client_y: int,
        *,
        bring_foreground: bool = True,
        hover_dwell_s: float | None = None,
        hold_s: float | None = None,
    ) -> bool:
        """物理路径（Maa SeizeInput）：置前 → ClientToScreen → SetCursorPos → SendInput 左键。"""
        src = int(hwnd)
        if src <= 0 or not _user32.IsWindow(wintypes.HWND(src)):
            return False
        cx, cy = int(client_x), int(client_y)
        prev_dpi = None
        if _set_thread_dpi_ctx is not None:
            prev_dpi = _set_thread_dpi_ctx(wintypes.HANDLE(_DPI_AWARE_PER_MONITOR_V2))
        try:
            if bring_foreground:
                _ensure_foreground_and_topmost(src)
            pt = _POINT(cx, cy)
            if not _user32.ClientToScreen(wintypes.HWND(src), ctypes.byref(pt)):
                return False
            sx, sy = int(pt.x), int(pt.y)
            if not _user32.SetCursorPos(sx, sy):
                return False
            skip_h, hd = _hover_skip_and_seconds(hover_dwell_s)
            if not skip_h:
                time.sleep(hd)
            inp_sz = ctypes.sizeof(_INPUT)
            inp_down = _INPUT()
            inp_down.type = _INPUT_MOUSE
            inp_down.mi.dwFlags = _MOUSEEVENTF_LEFTDOWN
            if _user32.SendInput(1, ctypes.byref(inp_down), inp_sz) != 1:
                return False
            hold = MOUSE_CLICK_HOLD_S if hold_s is None else max(0.0, float(hold_s))
            time.sleep(hold)
            inp_up = _INPUT()
            inp_up.type = _INPUT_MOUSE
            inp_up.mi.dwFlags = _MOUSEEVENTF_LEFTUP
            return _user32.SendInput(1, ctypes.byref(inp_up), inp_sz) == 1
        finally:
            if prev_dpi is not None and _set_thread_dpi_ctx is not None:
                _set_thread_dpi_ctx(prev_dpi)

else:

    def send_key_tap(hwnd: int, vk: int) -> bool:
        _ = hwnd, vk
        return True

    def send_key_down(hwnd: int, vk: int) -> bool:
        _ = hwnd, vk
        return True

    def send_key_up(hwnd: int, vk: int) -> bool:
        _ = hwnd, vk
        return True

    def send_hover_at(hwnd: int, client_x: int, client_y: int, *, dwell_s: float | None = None) -> bool:
        _ = hwnd, client_x, client_y, dwell_s
        return True

    def send_left_down(hwnd: int, client_x: int, client_y: int) -> bool:
        _ = hwnd, client_x, client_y
        return True

    def send_left_up(hwnd: int, client_x: int, client_y: int) -> bool:
        _ = hwnd, client_x, client_y
        return True

    def send_left_click(
        hwnd: int,
        client_x: int,
        client_y: int,
        *,
        hold_s: float | None = None,
        hover_dwell_s: float | None = None,
    ) -> bool:
        _ = hwnd, client_x, client_y, hold_s, hover_dwell_s
        return True

    def send_left_click_physical(
        hwnd: int,
        client_x: int,
        client_y: int,
        *,
        bring_foreground: bool = True,
        hover_dwell_s: float | None = None,
        hold_s: float | None = None,
    ) -> bool:
        _ = hwnd, client_x, client_y, bring_foreground, hover_dwell_s, hold_s
        return True
