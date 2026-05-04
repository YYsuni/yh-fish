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


_ADMIN_WARN_TEXT = (
    "【提示】当前未以管理员身份运行，键鼠模拟等功能可能无效；请关闭后右键「以管理员身份运行」启动本程序。"
)
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
