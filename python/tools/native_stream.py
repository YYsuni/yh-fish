# -*- coding: utf-8 -*-
"""Windows.Graphics.Capture（windows_capture）：按 HWND 异步抓帧并编码为 JPEG。"""

from __future__ import annotations

import io
import sys
import threading
import time

import numpy as np
from PIL import Image
from tools.exec_msg import msg_out


def native_backend_available() -> bool:
    """当前进程能否导入 `windows_capture`（仅 Win32 有意义）。"""
    if sys.platform != "win32":
        return False
    try:
        import windows_capture  # noqa: F401
    except ImportError:
        return False
    return True


class WgcHwndStreamer:
    """封装单 HWND 的 WGC 捕获线程，维护最近一次 JPEG 快照。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: tuple[bytes, int, int] | None = None
        self._err: str | None = None
        self._active_hwnd: int | None = None
        self._control = None
        self._cap = None

    def get_snapshot(self) -> tuple[bytes | None, int, int, str | None]:
        """取出最近一次编码成功的 JPEG 及宽高；无帧时 data 为 None。"""
        with self._lock:
            err = self._err
            if self._latest is None:
                return None, 0, 0, err
            data, w, h = self._latest
            return data, w, h, err

    def shutdown(self) -> None:
        """停止捕获并清空缓存。"""
        self._stop_inner()
        with self._lock:
            self._latest = None
            self._err = None

    def ensure_hwnd(self, hwnd: int | None, *, quality: int, min_interval_ms: float) -> None:
        """切换或清空目标窗口；同一 HWND 且已在跑则不变。"""
        if hwnd is None or int(hwnd) <= 0:
            self._stop_inner()
            with self._lock:
                self._latest = None
                self._err = "等待匹配游戏窗口…"
            return

        hwnd = int(hwnd)
        if hwnd == self._active_hwnd and self._control is not None:
            return

        self._stop_inner()
        try:
            self._start_for_hwnd(hwnd, quality=quality, min_interval_ms=min_interval_ms)
        except Exception as e:  # noqa: BLE001
            with self._lock:
                self._err = f"WGC 启动失败：{e}"
                msg_out(self._err)
                self._latest = None
                self._active_hwnd = None

    def _stop_inner(self) -> None:
        """停止当前 WindowsCapture 控制对象。"""
        c = self._control
        self._control = None
        self._cap = None
        self._active_hwnd = None
        if c is None:
            return
        try:
            c.stop()
            c.wait()
        except Exception:  # noqa: BLE001
            pass

    def _start_for_hwnd(self, hwnd: int, *, quality: int, min_interval_ms: float) -> None:
        """为指定 HWND 启动自由线程捕获，在帧回调里节流编码 JPEG。"""
        from windows_capture import WindowsCapture

        cap = WindowsCapture(window_hwnd=hwnd, cursor_capture=False, draw_border=False)
        last_encode = [0.0]
        first_frame_logged = [False]

        @cap.event
        def on_closed() -> None:
            """捕获会话关闭（占位，无需处理）。"""
            msg_out(f"WGC 捕获会话关闭 hwnd: {hwnd}")
            return

        @cap.event
        def on_frame_arrived(frame, _internal_capture_control):  # noqa: F841
            """新帧到达：按最小间隔将 BGRA 缓冲转为 JPEG 写入 `_latest`。"""
            if not first_frame_logged[0]:
                msg_out(f"捕获第一帧成功 hwnd: {hwnd}")
                first_frame_logged[0] = True
            now = time.monotonic()
            if (now - last_encode[0]) * 1000.0 < min_interval_ms:
                return
            last_encode[0] = now
            try:
                h, w, _ = frame.frame_buffer.shape
                raw = np.ascontiguousarray(frame.frame_buffer).tobytes()
                img = Image.frombytes("RGBA", (w, h), raw, "raw", "BGRA").convert("RGB")
                bio = io.BytesIO()
                img.save(bio, format="JPEG", quality=quality, optimize=False)
                data = bio.getvalue()
                with self._lock:
                    self._latest = (data, w, h)
                    self._err = None
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    self._err = str(e)

        control = cap.start_free_threaded()
        self._cap = cap
        self._control = control
        self._active_hwnd = hwnd
        msg_out(f"启动WGC成功 hwnd: {hwnd}")