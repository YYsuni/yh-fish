# -*- coding: utf-8 -*-

from __future__ import annotations

import io
import sys
import threading
import time
from dataclasses import dataclass

from PIL import Image

# 与 MaaNTE interface.json 中 window_regex 语义接近：标题为「异环」或「NTE」
DEFAULT_TITLE_REGEX = r"^\s*(异环|NTE)\s*$"


def _placeholder_jpeg(text: str = "未找到游戏窗口") -> bytes:
    img = Image.new("RGB", (640, 360), (248, 250, 252))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    # 纯底图即可；文字需 Pillow 绘图，保持依赖最小，仅用单色底
    return buf.getvalue()


@dataclass
class CaptureStatus:
    ok: bool
    title_regex: str
    hwnd: int | None
    width: int
    height: int
    fps: float
    message: str


class CaptureService:
    def __init__(self, *, title_regex: str = DEFAULT_TITLE_REGEX, fps: float = 15.0) -> None:
        self._title_regex = title_regex
        self._fps = max(1.0, min(fps, 60.0))
        self._lock = threading.Lock()
        self._latest: bytes = _placeholder_jpeg()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._size = (0, 0)
        self._msg = ""

    @property
    def title_regex(self) -> str:
        return self._title_regex

    def set_title_regex(self, pattern: str) -> None:
        p = (pattern or "").strip()
        if p:
            self._title_regex = p

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
            t.join(timeout=2.0)

    def get_jpeg(self) -> bytes:
        with self._lock:
            return self._latest

    def get_status(self) -> CaptureStatus:
        with self._lock:
            w, h = self._size
            return CaptureStatus(
                ok=self._hwnd is not None and w > 0,
                title_regex=self._title_regex,
                hwnd=self._hwnd,
                width=w,
                height=h,
                fps=self._fps,
                message=self._msg,
            )

    def _loop(self) -> None:
        if sys.platform != "win32":
            self._set_frame(_placeholder_jpeg(), None, 0, 0, "仅支持 Windows 窗口捕获")
            return

        from window_capture import find_game_hwnd, grab_client_jpeg

        interval = 1.0 / self._fps
        while not self._stop.is_set():
            hwnd = find_game_hwnd(self._title_regex)
            if hwnd is None:
                self._set_frame(
                    _placeholder_jpeg(),
                    None,
                    0,
                    0,
                    f"未匹配窗口（正则 {self._title_regex!r}）",
                )
                time.sleep(interval)
                continue

            data, w, h = grab_client_jpeg(hwnd)
            if not data:
                self._set_frame(
                    _placeholder_jpeg(),
                    hwnd,
                    0,
                    0,
                    "截图失败（窗口可能被遮挡或最小化）",
                )
                time.sleep(interval)
                continue

            self._set_frame(data, hwnd, w, h, "实时预览")
            time.sleep(interval)

    def _set_frame(self, jpeg: bytes, hwnd: int | None, w: int, h: int, msg: str) -> None:
        with self._lock:
            self._latest = jpeg
            self._hwnd = hwnd
            self._size = (w, h)
            self._msg = msg
