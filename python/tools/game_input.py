# -*- coding: utf-8 -*-
"""游戏窗口输入：键盘 PostMessage；鼠标分消息路径 `send_left_click` 与物理路径 `send_left_click_physical`（置前+SendInput）。"""

from __future__ import annotations

import sys
import time
from typing import Callable

_click_offset_provider: Callable[[], tuple[int, int]] | None = None


def set_click_offset_provider(fn: Callable[[], tuple[int, int]] | None) -> None:
    """注册从应用设置读取 ``(click_offset_x, click_offset_y)`` 的回调；供 ``send_left_click_physical`` 在 ``from_precrop=True`` 时使用。"""
    global _click_offset_provider
    _click_offset_provider = fn


VK_E = 0x45
VK_F = 0x46
VK_A = 0x41
VK_D = 0x44
VK_J = 0x4A
VK_K = 0x4B
VK_SPACE = 0x20
VK_ESCAPE = 0x1B

KEYBOARD_ACTIVATE_DELAY_S = 0.01
MOUSE_ACTIVATE_DELAY_S = 0.02
MOUSE_STEP_DELAY_S = 0.03
MOUSE_CLICK_HOLD_S = 0.2
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
    _SWP_TOP_FLAGS = _SWP_NOMOVE | _SWP_NOSIZE

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
        """合并 16 位低字 lo 与高字 hi 为 32 位 LPARAM。"""
        return int((hi & 0xFFFF) << 16 | (lo & 0xFFFF))

    def _hover_skip_and_seconds(hover_dwell_s: float | None) -> tuple[bool, float]:
        """解析悬停时长：显式 `<=0` 表示跳过悬停；否则返回 (是否跳过, 秒数)。"""
        if hover_dwell_s is not None and float(hover_dwell_s) <= 0:
            return True, 0.0
        sec = MOUSE_HOVER_DWELL_S if hover_dwell_s is None else max(0.0, float(hover_dwell_s))
        return False, sec

    def _hwnd_int(h: wintypes.HWND | None) -> int:
        """HWND 转 int，空或无句柄时返回 0。"""
        return int(h) if h else 0

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
        """是否同一 GA_ROOT 顶层根窗口（用于前台判断，避免子窗与顶层句柄误判）。"""
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
        c = _hwnd_int(cap)
        if c and _user32.IsWindow(wintypes.HWND(c)) and _same_root_hwnd(c, source_hwnd):
            return c
        return _delivery_hwnd_lbutton_down(source_hwnd, cx, cy)

    def _mouse_ctx(hwnd: int, client_x: int, client_y: int, *, up: bool) -> tuple[int, int, int, int] | None:
        """校验 hwnd 并返回 (src, cx, cy, delivery)；无效时 None。`up` 选择抬起/按下投递 HWND 规则。"""
        src = int(hwnd)
        if src <= 0 or not _user32.IsWindow(wintypes.HWND(src)):
            return None
        cx, cy = int(client_x), int(client_y)
        d = _delivery_hwnd_lbutton_up(src, cx, cy) if up else _delivery_hwnd_lbutton_down(src, cx, cy)
        return None if d <= 0 else (src, cx, cy, d)

    def _ensure_foreground_and_topmost(hwnd: int) -> None:
        """Maa InputUtils::ensure_foreground_and_topmost：置顶 Z 序并 SetForegroundWindow；同根已在台前则早退。"""
        if hwnd <= 0 or not _user32.IsWindow(wintypes.HWND(hwnd)):
            return
        h = wintypes.HWND(hwnd)
        fg_i = _hwnd_int(_user32.GetForegroundWindow())
        if fg_i and _same_root_hwnd(int(hwnd), fg_i):
            return
        _user32.SetWindowPos(h, wintypes.HWND(_HWND_TOP), 0, 0, 0, 0, _SWP_TOP_FLAGS | _SWP_SHOWWINDOW)
        time.sleep(0.005)
        _user32.SetForegroundWindow(h)
        time.sleep(0.01)
        fg2_i = _hwnd_int(_user32.GetForegroundWindow())
        if fg2_i and not _same_root_hwnd(int(hwnd), fg2_i):
            _user32.SetWindowPos(h, wintypes.HWND(_HWND_TOP), 0, 0, 0, 0, _SWP_TOP_FLAGS)
            time.sleep(0.005)

    def _send_activate(target: int, *, sync: bool) -> None:
        """发送 WM_ACTIVATE(WA_ACTIVE)；sync 为 True 时 SendMessage + 鼠标路径延迟，否则 Post + 键盘路径延迟。"""
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return
        t = wintypes.HWND(target)
        wparam, lparam = wintypes.WPARAM(WA_ACTIVE), wintypes.LPARAM(0)
        if sync:
            _user32.SendMessageW(t, WM_ACTIVATE, wparam, lparam)
            time.sleep(MOUSE_ACTIVATE_DELAY_S)
        else:
            _user32.PostMessageW(t, WM_ACTIVATE, wparam, lparam)
            time.sleep(KEYBOARD_ACTIVATE_DELAY_S)

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

    def _make_key_lparam(vk: int, *, key_up: bool) -> int:
        """构造键盘消息的 LPARAM（扫描码、repeat 计数；抬起含 transition 位）。"""
        sc = int(_user32.MapVirtualKeyW(vk & 0xFF, MAPVK_VK_TO_VSC)) & 0xFF
        lp = 1 | (sc << 16)
        return lp | ((1 << 30) | (1 << 31)) if key_up else lp

    def _post_key(target: int, vk: int, *, key_up: bool) -> bool:
        """键盘路径：Post WM_ACTIVATE 后 Post KEYDOWN 或 KEYUP。"""
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return False
        vk_i = int(vk) & 0xFF
        _send_activate(target, sync=False)
        msg = WM_KEYUP if key_up else WM_KEYDOWN
        return bool(
            _user32.PostMessageW(
                wintypes.HWND(target),
                msg,
                wintypes.WPARAM(vk_i),
                wintypes.LPARAM(_make_key_lparam(vk_i, key_up=key_up)),
            )
        )

    def _send_mouse_sync(target: int, source_hwnd: int, msg: int, wparam: int, cx: int, cy: int) -> bool:
        """SendMessageW 同步投递一条鼠标消息（坐标经 _make_mouse_lparam）。"""
        if target <= 0 or not _user32.IsWindow(wintypes.HWND(target)):
            return False
        lp = _make_mouse_lparam(source_hwnd, target, cx, cy)
        _user32.SendMessageW(wintypes.HWND(target), msg, wintypes.WPARAM(wparam), wintypes.LPARAM(lp))
        return True

    def _send_input_mouse(dw_flags: int) -> bool:
        """SendInput 注入一条鼠标 INPUT（type=MOUSE，dwFlags 为左键按下/抬起等）。"""
        inp = _INPUT()
        inp.type = _INPUT_MOUSE
        inp.mi.dwFlags = dw_flags
        sz = ctypes.sizeof(_INPUT)
        return _user32.SendInput(1, ctypes.byref(inp), sz) == 1

    def send_key_tap(hwnd: int, vk: int, *, hold_between_down_up_s: float = 0.0) -> bool:
        """KEYDOWN → 可选间隔 → KEYUP；间隔为按下与抬起之间的秒数。"""
        t = _get_active_hwnd(hwnd)
        if not _post_key(t, vk, key_up=False):
            return False
        h = max(0.0, float(hold_between_down_up_s))
        if h > 0:
            time.sleep(h)
        return _post_key(t, vk, key_up=True)

    def send_key_down(hwnd: int, vk: int) -> bool:
        """对活动子窗 Post KEYDOWN。"""
        return _post_key(_get_active_hwnd(hwnd), vk, key_up=False)

    def send_key_up(hwnd: int, vk: int) -> bool:
        """对活动子窗 Post KEYUP。"""
        return _post_key(_get_active_hwnd(hwnd), vk, key_up=True)

    def send_hover_at(hwnd: int, client_x: int, client_y: int, *, dwell_s: float | None = None) -> bool:
        """WM_MOUSEMOVE(0) → TrackMouseEvent(TME_HOVER) → sleep(dwell) → WM_MOUSEMOVE(0)。"""
        ctx = _mouse_ctx(hwnd, client_x, client_y, up=False)
        if not ctx:
            return False
        src, cx, cy, delivery = ctx
        _send_activate(delivery, sync=True)
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
        ctx = _mouse_ctx(hwnd, client_x, client_y, up=False)
        if not ctx:
            return False
        src, cx, cy, delivery = ctx
        _send_activate(delivery, sync=True)
        if not _send_mouse_sync(delivery, src, WM_MOUSEMOVE, MK_LBUTTON, cx, cy):
            return False
        time.sleep(MOUSE_STEP_DELAY_S)
        return _send_mouse_sync(delivery, src, WM_LBUTTONDOWN, MK_LBUTTON, cx, cy)

    def send_left_up(hwnd: int, client_x: int, client_y: int) -> bool:
        """SendMessage：MOVE(0) → LBUTTONUP（投递 HWND 见 _delivery_hwnd_lbutton_up）。"""
        ctx = _mouse_ctx(hwnd, client_x, client_y, up=True)
        if not ctx:
            return False
        src, cx, cy, delivery = ctx
        _send_activate(delivery, sync=True)
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
        """消息路径：可选 send_hover_at 后 down→hold→up；`hover_dwell_s=0` 跳过悬停段。"""
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
        x: int,
        y: int,
        *,
        from_precrop: bool = True,
        bring_foreground: bool = True,
        # 光标到位后、按下左键前的停留秒数；None 用 MOUSE_HOVER_DWELL_S；<=0 跳过悬停
        hover_dwell_s: float | None = None,
        # 左键按下到抬起之间的保持秒数；None 用 MOUSE_CLICK_HOLD_S
        hold_s: float | None = None,
    ) -> bool:
        """物理左键：可选置前 + 本线程临时 Per-Monitor V2 DPI + SetCursorPos + SendInput（与消息路径不同）。

        ``from_precrop=True``（默认）：``x``/``y`` 为 **WGC 整帧** 与 ``capture_service`` 解码前 JPEG 同坐标系的像素；
        本函数内先按 ``wgc_precrop_xy_to_client`` 规则（将 ``app-settings.json`` 中 ``click_offset_x`` / ``click_offset_y`` 加到换算结果上）得到 HWND 客户区坐标，再 ``ClientToScreen``。

        ``from_precrop=False``：``x``/``y`` 已为 **客户区** 像素（例如模板匹配在裁剪后画面上得到的矩形中心），不做整窗换算。
        """
        from tools.window_capture import wgc_precrop_xy_to_client

        src = int(hwnd)
        if src <= 0 or not _user32.IsWindow(wintypes.HWND(src)):
            return False
        if from_precrop:
            ox, oy = 0, 0
            prov = _click_offset_provider
            if prov is not None:
                try:
                    ox, oy = prov()
                except Exception:
                    ox, oy = (0, 0)
            cx, cy = wgc_precrop_xy_to_client(src, int(x), int(y), offset_x=int(ox), offset_y=int(oy))
        else:
            cx, cy = int(x), int(y)
        prev_dpi = None
        if _set_thread_dpi_ctx is not None:
            prev_dpi = _set_thread_dpi_ctx(wintypes.HANDLE(_DPI_AWARE_PER_MONITOR_V2))
        try:
            focus_hwnd = _get_active_hwnd(src)
            if bring_foreground and focus_hwnd > 0:
                _ensure_foreground_and_topmost(focus_hwnd)
            pt = _POINT(cx, cy)
            if not _user32.ClientToScreen(wintypes.HWND(src), ctypes.byref(pt)):
                return False
            sx, sy = int(pt.x), int(pt.y)
            if not _user32.SetCursorPos(sx, sy):
                return False
            skip_h, hd = _hover_skip_and_seconds(hover_dwell_s)
            if not skip_h:
                time.sleep(hd)
            if not _send_input_mouse(_MOUSEEVENTF_LEFTDOWN):
                return False
            hold = MOUSE_CLICK_HOLD_S if hold_s is None else max(0.0, float(hold_s))
            time.sleep(hold)
            return _send_input_mouse(_MOUSEEVENTF_LEFTUP)
        finally:
            if prev_dpi is not None and _set_thread_dpi_ctx is not None:
                _set_thread_dpi_ctx(prev_dpi)

else:

    def send_key_tap(hwnd: int, vk: int, *, hold_between_down_up_s: float = 0.0) -> bool:
        """非 Windows 占位：恒返回 True（与 win32 分支 API 对齐）。"""
        return True

    def send_key_down(hwnd: int, vk: int) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True

    def send_key_up(hwnd: int, vk: int) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True

    def send_hover_at(hwnd: int, client_x: int, client_y: int, *, dwell_s: float | None = None) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True

    def send_left_down(hwnd: int, client_x: int, client_y: int) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True

    def send_left_up(hwnd: int, client_x: int, client_y: int) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True

    def send_left_click(
        hwnd: int,
        client_x: int,
        client_y: int,
        *,
        hold_s: float | None = None,
        hover_dwell_s: float | None = None,
    ) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True

    def send_left_click_physical(
        hwnd: int,
        x: int,
        y: int,
        *,
        from_precrop: bool = True,
        bring_foreground: bool = True,
        hover_dwell_s: float | None = None,
        hold_s: float | None = None,
    ) -> bool:
        """非 Windows 占位：恒返回 True。"""
        return True
