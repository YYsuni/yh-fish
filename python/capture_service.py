# -*- coding: utf-8 -*-
"""游戏窗口捕获：WGC 取整窗 JPEG → 裁标题栏与边缘 → 后台线程按 FPS 更新最新帧。"""

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
        """非 Windows 无 WGC，视为后端不可用。"""
        return False

    WgcHwndStreamer = None

DEFAULT_TITLE_REGEX = r"^\s*(异环|NTE)\s*$"
JPEG_QUALITY = 72
CROP_MARGIN_LR_PX = 2
CROP_MARGIN_BOTTOM_PX = 2
FPS_MIN = 1.0
FPS_MAX = 60.0

_placeholder_jpeg_cache: bytes | None = None


def _clamp_fps(v: float) -> float:
    """将 FPS 限制在 [FPS_MIN, FPS_MAX]。"""
    return max(FPS_MIN, min(float(v), FPS_MAX))


def _placeholder_jpeg() -> bytes:
    """无窗口或捕获失败时使用的占位 JPEG（单例缓存）。"""
    global _placeholder_jpeg_cache
    if _placeholder_jpeg_cache is None:
        img = Image.new("RGB", (640, 360), (248, 250, 252))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        _placeholder_jpeg_cache = buf.getvalue()
    return _placeholder_jpeg_cache


def _crop_jpeg_capture(
    jpeg: bytes,
    title_top_px: int,
    quality: int,
) -> tuple[bytes, int, int] | None:
    """裁掉标题栏高度与左右/底边距后重新编码 JPEG；失败返回 None。"""
    try:
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    except OSError:
        return None
    w, h = img.size
    t = max(0, title_top_px)
    x0 = CROP_MARGIN_LR_PX
    y0 = t
    x1 = w - CROP_MARGIN_LR_PX
    y1 = h - CROP_MARGIN_BOTTOM_PX
    if x1 <= x0 or y1 <= y0:
        return None
    cropped = img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    cropped.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), x1 - x0, y1 - y0


@dataclass
class CaptureStatus:
    """`/api/capture/status` 返回的结构（内存中的同源模型）。"""

    ok: bool
    hwnd: int | None
    width: int
    height: int
    fps: float


class CaptureService:
    """匹配游戏 HWND、驱动 WGC、维护 `_latest` JPEG 与状态。"""

    def __init__(self, *, title_regex: str = DEFAULT_TITLE_REGEX, fps: float = 15.0) -> None:
        self._title_regex = title_regex
        self._fps = _clamp_fps(fps)
        self._lock = threading.Lock()
        self._latest: bytes = _placeholder_jpeg()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._size = (0, 0)

        self._has_wgc = native_backend_available() and sys.platform == "win32"
        self._wgc = WgcHwndStreamer() if (self._has_wgc and WgcHwndStreamer is not None) else None

    def set_fps(self, fps: float) -> float:
        """设置捕获循环目标帧率并返回钳制后的值。"""
        with self._lock:
            self._fps = _clamp_fps(fps)
            return self._fps

    def mjpeg_sleep_s(self) -> float:
        """MJPEG 流 generator 每次推送后的休眠秒数（与当前 FPS 一致）。"""
        with self._lock:
            return 1.0 / self._fps

    def start_background(self) -> None:
        """启动后台捕获线程（幂等）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="capture", daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        """停止捕获线程并关闭 WGC。"""
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        if self._wgc:
            self._wgc.shutdown()

    def get_jpeg(self) -> bytes:
        """返回当前最新一帧 JPEG（线程安全副本引用）。"""
        with self._lock:
            return self._latest

    def get_status(self) -> CaptureStatus:
        """返回 UI/API 需要的窗口与 FPS 摘要。"""
        with self._lock:
            w, h = self._size
            return CaptureStatus(
                ok=self._hwnd is not None and w > 0,
                hwnd=self._hwnd,
                width=w,
                height=h,
                fps=self._fps,
            )

    def _loop(self) -> None:
        """按 FPS 循环：找窗口 → WGC 快照 → 裁切 → 写入 `_latest`。"""
        if sys.platform != "win32" or self._wgc is None:
            self._set_frame(_placeholder_jpeg(), None, 0, 0)
            return

        from window_capture import find_game_hwnd, window_title_bar_crop_px

        while not self._stop.is_set():
            with self._lock:
                fps = self._fps
            interval = 1.0 / fps
            min_iv = max(1000.0 / fps / 2.0, 8.0)

            hwnd = find_game_hwnd(self._title_regex)
            if hwnd is None:
                self._wgc.ensure_hwnd(None, quality=JPEG_QUALITY, min_interval_ms=min_iv)
                self._set_frame(_placeholder_jpeg(), None, 0, 0)
                time.sleep(interval)
                continue

            self._wgc.ensure_hwnd(hwnd, quality=JPEG_QUALITY, min_interval_ms=min_iv)
            data, w, h, _ = self._wgc.get_snapshot()
            if data:
                chop = window_title_bar_crop_px(hwnd)
                out = _crop_jpeg_capture(data, chop, JPEG_QUALITY)
                if out is not None:
                    data, w, h = out
                self._set_frame(data, hwnd, w, h)
            else:
                self._set_frame(_placeholder_jpeg(), hwnd, 0, 0)
            time.sleep(interval)

    def _set_frame(self, jpeg: bytes, hwnd: int | None, w: int, h: int) -> None:
        """原子更新最新帧与 HWND、输出尺寸。"""
        with self._lock:
            self._latest = jpeg
            self._hwnd = hwnd
            self._size = (w, h)
