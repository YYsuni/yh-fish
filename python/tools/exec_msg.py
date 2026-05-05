# -*- coding: utf-8 -*-
"""执行过程文本输出：内存环形缓冲，供 GET /api/msg/log 拉取。"""

from __future__ import annotations

import sys
import threading
import time
from collections import deque
from typing import Any

_MAX = 400
_lines: deque[tuple[float, str]] = deque(maxlen=_MAX)
_lock = threading.Lock()


def msg_out(text: str) -> None:
    with _lock:
        _lines.append((time.time(), text))


def snapshot() -> list[dict[str, Any]]:
    with _lock:
        return [{"t": t, "m": m} for t, m in _lines]


def runs_as_elevated() -> bool:
    """Windows 下是否为管理员进程；非 Windows 视为已满足（开发机不打扰）。"""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


_ADMIN_WARN_TEXT = "【提示】当前未以管理员身份运行，键鼠模拟等功能可能无效；请关闭后右键「以管理员身份运行」启动本程序。"

# 与模板/自动化坐标系一致：游戏客户区（裁标题栏与边距后）逻辑分辨率。
REQUIRED_CLIENT_WIDTH = 1280
REQUIRED_CLIENT_HEIGHT = 720
_WINDOW_SIZE_TOLERANCE_PX = 3

_window_size_warn_lock = threading.Lock()
_last_window_size_warn_mono = 0.0
_WINDOW_SIZE_WARN_INTERVAL_S = 3.0

_NON_WINDOWS_GAME_HWND_WARN_TEXT = "【提示】当前平台非 Windows，无法按标题匹配游戏窗口 HWND；整窗捕获与相关自动化仅在 Windows 下可用。"
_non_windows_game_hwnd_warn_lock = threading.Lock()
_last_non_windows_game_hwnd_warn_mono = 0.0
_NON_WINDOWS_GAME_HWND_WARN_INTERVAL_S = 5.0


def maybe_warn_window_size(cw: int, ch: int) -> None:
    """裁剪后逻辑尺寸与 1280×720 相差超过容差时，节流写入 msg 日志（避免每帧刷屏）。"""
    global _last_window_size_warn_mono
    if cw <= 0 or ch <= 0:
        return
    if abs(cw - REQUIRED_CLIENT_WIDTH) <= _WINDOW_SIZE_TOLERANCE_PX and abs(ch - REQUIRED_CLIENT_HEIGHT) <= _WINDOW_SIZE_TOLERANCE_PX:
        return
    now = time.monotonic()
    with _window_size_warn_lock:
        if now - _last_window_size_warn_mono < _WINDOW_SIZE_WARN_INTERVAL_S:
            return
        _last_window_size_warn_mono = now
    msg_out(f"【提示】游戏窗口客户区当前为 {cw}×{ch}，请设为 {REQUIRED_CLIENT_WIDTH}×{REQUIRED_CLIENT_HEIGHT}，" "否则模板匹配与自动化可能异常。")


def maybe_warn_non_windows_game_hwnd() -> None:
    """非 Windows 下按间隔节流写入 HWND 相关提示（避免刷屏）。"""
    global _last_non_windows_game_hwnd_warn_mono
    now = time.monotonic()
    with _non_windows_game_hwnd_warn_lock:
        if now - _last_non_windows_game_hwnd_warn_mono < _NON_WINDOWS_GAME_HWND_WARN_INTERVAL_S:
            return
        _last_non_windows_game_hwnd_warn_mono = now
    msg_out(_NON_WINDOWS_GAME_HWND_WARN_TEXT)


_admin_warn_stop = threading.Event()
_admin_warn_thread: threading.Thread | None = None
_admin_warn_start_lock = threading.Lock()


def _admin_warn_worker() -> None:
    while True:
        if _admin_warn_stop.is_set():
            return
        if not runs_as_elevated():
            msg_out(_ADMIN_WARN_TEXT)
        if _admin_warn_stop.wait(3.0):
            return


def start_admin_warn_loop() -> None:
    """非管理员时每 3 秒往 msg 日志追加一行提示（与现有终端轮询共用）。"""
    global _admin_warn_thread
    with _admin_warn_start_lock:
        if _admin_warn_thread is not None and _admin_warn_thread.is_alive():
            return
        _admin_warn_stop.clear()
        _admin_warn_thread = threading.Thread(target=_admin_warn_worker, name="admin-warn", daemon=True)
        _admin_warn_thread.start()


def stop_admin_warn_loop() -> None:
    _admin_warn_stop.set()
