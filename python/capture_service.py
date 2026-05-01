# -*- coding: utf-8 -*-

from __future__ import annotations

import io
import sys
import threading
import time
from dataclasses import dataclass

from PIL import Image

if sys.platform == "win32":
    from native_stream import WgcHwndStreamer, native_backend_available
else:

    def native_backend_available() -> bool:
        return False

    WgcHwndStreamer = None

DEFAULT_TITLE_REGEX = r"^\s*(异环|NTE)\s*$"
JPEG_QUALITY = 72
FPS_MIN = 1.0
FPS_MAX = 60.0


def _clamp_fps(v: float) -> float:
    return max(FPS_MIN, min(float(v), FPS_MAX))


def _placeholder_jpeg() -> bytes:
    img = Image.new("RGB", (640, 360), (248, 250, 252))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@dataclass
class CaptureStatus:
    ok: bool
    hwnd: int | None
    width: int
    height: int
    fps: float
    message: str


class CaptureService:

    def __init__(self, *, title_regex: str = DEFAULT_TITLE_REGEX, fps: float = 30.0) -> None:
        self._title_regex = title_regex
        self._fps = _clamp_fps(fps)
        self._lock = threading.Lock()
        self._latest: bytes = _placeholder_jpeg()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._size = (0, 0)
        self._msg = "捕获线程启动中…"

        self._has_wgc = native_backend_available() and sys.platform == "win32"
        self._wgc = WgcHwndStreamer() if (self._has_wgc and WgcHwndStreamer is not None) else None

    def set_fps(self, fps: float) -> float:
        with self._lock:
            self._fps = _clamp_fps(fps)
            return self._fps

    def mjpeg_sleep_s(self) -> float:
        with self._lock:
            return 1.0 / self._fps

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="capture", daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        if self._wgc:
            self._wgc.shutdown()

    def get_jpeg(self) -> bytes:
        with self._lock:
            return self._latest

    def get_status(self) -> CaptureStatus:
        with self._lock:
            w, h = self._size
            return CaptureStatus(
                ok=self._hwnd is not None and w > 0,
                hwnd=self._hwnd,
                width=w,
                height=h,
                fps=self._fps,
                message=self._msg,
            )

    def _loop(self) -> None:
        if sys.platform != "win32":
            self._set_frame(_placeholder_jpeg(), None, 0, 0, "仅支持 Windows")
            return

        if self._wgc is None:
            self._set_frame(
                _placeholder_jpeg(),
                None,
                0,
                0,
                "未安装 windows-capture：pip install -r python/requirements.txt",
            )
            return

        from window_capture import find_game_hwnd

        while not self._stop.is_set():
            with self._lock:
                fps = self._fps
            interval = 1.0 / fps
            min_iv = max(1000.0 / fps / 2.0, 8.0)

            hwnd = find_game_hwnd(self._title_regex)
            if hwnd is None:
                self._wgc.ensure_hwnd(None, quality=JPEG_QUALITY, min_interval_ms=min_iv)
                self._set_frame(
                    _placeholder_jpeg(),
                    None,
                    0,
                    0,
                    f"未匹配窗口（正则 {self._title_regex!r}）",
                )
                time.sleep(interval)
                continue

            self._wgc.ensure_hwnd(hwnd, quality=JPEG_QUALITY, min_interval_ms=min_iv)
            data, w, h, werr = self._wgc.get_snapshot()
            if data:
                self._set_frame(data, hwnd, w, h, "WGC 预览")
            else:
                detail = werr or "等待第一帧（勿最小化游戏窗口）"
                self._set_frame(
                    _placeholder_jpeg(),
                    hwnd,
                    0,
                    0,
                    f"WGC：{detail}",
                )
            time.sleep(interval)

    def _set_frame(self, jpeg: bytes, hwnd: int | None, w: int, h: int, msg: str) -> None:
        with self._lock:
            self._latest = jpeg
            self._hwnd = hwnd
            self._size = (w, h)
            self._msg = msg
