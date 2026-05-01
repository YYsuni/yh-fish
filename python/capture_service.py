# -*- coding: utf-8 -*-
"""游戏窗口捕获：WGC 取整窗 JPEG → 裁标题栏与边缘 → 编码为预览格式并按 FPS 更新最新帧。"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

from PIL import Image

from page_template_match import PageTemplateMatcher

if sys.platform == "win32":
    from native_stream import WgcHwndStreamer, native_backend_available
else:

    def native_backend_available() -> bool:
        """非 Windows 无 WGC，视为后端不可用。"""
        return False

    WgcHwndStreamer = None

DEFAULT_TITLE_REGEX = r"^\s*(异环|NTE)\s*$"
JPEG_QUALITY = 72
WEBP_QUALITY = 78
WEBP_METHOD = 3
CROP_MARGIN_LR_PX = 2
CROP_MARGIN_BOTTOM_PX = 2
PREVIEW_MAX_WIDTH = 600
FPS_MIN = 1.0
FPS_MAX = 60.0
LIVE_FPS_WINDOW_S = 1.0

_requested_codec = os.environ.get("YH_FISH_PREVIEW_CODEC", "jpeg").strip().lower()
if _requested_codec not in ("jpeg", "webp"):
    _requested_codec = "jpeg"


def _webp_supported() -> bool:
    """检测当前 Pillow 是否具备 WEBP 编码（依赖 libwebp）。"""
    try:
        Image.new("RGB", (4, 4)).save(io.BytesIO(), format="WEBP")
        return True
    except Exception:
        return False


_effective_preview_codec = "webp" if _requested_codec == "webp" and _webp_supported() else "jpeg"
if _requested_codec == "webp" and _effective_preview_codec != "webp":
    print(
        "YH_FISH_PREVIEW_CODEC=webp 但当前 Pillow 不支持 WEBP 编码，已回退为 jpeg",
        file=sys.stderr,
    )

_placeholder_jpeg_cache: bytes | None = None
_placeholder_webp_cache: bytes | None = None


def _clamp_fps(v: float) -> float:
    """将 FPS 限制在 [FPS_MIN, FPS_MAX]。"""
    return max(FPS_MIN, min(float(v), FPS_MAX))


def current_preview_mime() -> str:
    """预览二进制帧的 MIME（WS / MJPEG 分片 Content-Type）。"""
    return "image/webp" if _effective_preview_codec == "webp" else "image/jpeg"


def _placeholder_preview() -> bytes:
    """无窗口或捕获失败时的占位图（与当前预览编码一致）。"""
    global _placeholder_jpeg_cache, _placeholder_webp_cache
    img = Image.new("RGB", (640, 360), (248, 250, 252))
    img = _downscale_preview_max_width(img, PREVIEW_MAX_WIDTH)
    if _effective_preview_codec == "webp":
        if _placeholder_webp_cache is None:
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=70, method=WEBP_METHOD)
            _placeholder_webp_cache = buf.getvalue()
        return _placeholder_webp_cache
    if _placeholder_jpeg_cache is None:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        _placeholder_jpeg_cache = buf.getvalue()
    return _placeholder_jpeg_cache


def _downscale_preview_max_width(img: Image.Image, max_w: int) -> Image.Image:
    """预览输出：宽度大于 max_w 时按比例缩小（减轻编码与前端解码负担）。"""
    w, h = img.size
    if w <= max_w:
        return img
    new_h = max(1, int(round(h * max_w / w)))
    return img.resize((max_w, new_h), Image.Resampling.BILINEAR)


def _encode_preview_rgb(cropped: Image.Image) -> bytes:
    """
    将裁剪后的 RGB 图编码为预览字节。
    JPEG：optimize=False，降低 CPU；WebP：method=WEBP_METHOD，偏小 method 换更少编码耗时。
    本地环回带宽通常不是瓶颈，编码耗时更易拖累端到端帧延迟。
    """
    buf = io.BytesIO()
    if _effective_preview_codec == "webp":
        cropped.save(
            buf,
            format="WEBP",
            quality=WEBP_QUALITY,
            method=WEBP_METHOD,
        )
    else:
        cropped.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=False)
    return buf.getvalue()


def _decode_and_crop_rgb(jpeg: bytes, title_top_px: int) -> Image.Image | None:
    """解码 WGC JPEG 并裁客户区（去标题栏与边距），返回 RGB `Image`；失败返回 None。"""
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
    return img.crop((x0, y0, x1, y1))


def _encode_cropped_to_preview(cropped: Image.Image) -> tuple[bytes, int, int]:
    """将裁剪图按 PREVIEW_MAX_WIDTH 缩小后编码；返回 (字节, 逻辑裁剪宽, 逻辑裁剪高)。"""
    cw, ch = cropped.size
    scaled = _downscale_preview_max_width(cropped, PREVIEW_MAX_WIDTH)
    return _encode_preview_rgb(scaled), cw, ch


def _crop_to_preview(
    jpeg: bytes,
    title_top_px: int,
) -> tuple[bytes, int, int] | None:
    """解码、裁剪并编码预览；宽高为裁剪后的逻辑尺寸（与 `/status` 一致）。"""
    cropped = _decode_and_crop_rgb(jpeg, title_top_px)
    if cropped is None:
        return None
    raw, cw, ch = _encode_cropped_to_preview(cropped)
    return raw, cw, ch


@dataclass
class CaptureStatus:
    """`/api/capture/status` 返回的结构（内存中的同源模型）。"""

    ok: bool
    hwnd: int | None
    width: int
    height: int
    fps: float
    preview_mime: str
    page_match: dict[str, object] | None


def _page_match_dict(m: object) -> dict[str, object] | None:
    """将 `PageMatchResult` 转为可 JSON 序列化的 dict；无匹配返回 None。"""
    if m is None:
        return None
    return {
        "page_id": getattr(m, "page_id"),
        "page_label": getattr(m, "label"),
        "similarity": float(getattr(m, "confidence")),
        "x": int(getattr(m, "x")),
        "y": int(getattr(m, "y")),
        "w": int(getattr(m, "w")),
        "h": int(getattr(m, "h")),
    }


class CaptureService:
    """匹配游戏 HWND、驱动 WGC、维护 `_latest` 预览字节与状态。"""

    def __init__(self, *, title_regex: str = DEFAULT_TITLE_REGEX, fps: float = 15.0) -> None:
        self._title_regex = title_regex
        self._fps = _clamp_fps(fps)
        self._lock = threading.Lock()
        self._frame_ready = threading.Condition(self._lock)
        self._latest: bytes = _placeholder_preview()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd: int | None = None
        self._size = (0, 0)
        self._live_fps_times: deque[float] = deque()
        self._page_match: dict[str, object] | None = None
        self._page_matcher = PageTemplateMatcher()

        self._has_wgc = native_backend_available() and sys.platform == "win32"
        self._wgc = WgcHwndStreamer() if (self._has_wgc and WgcHwndStreamer is not None) else None

    def preview_mime(self) -> str:
        """当前预览帧 MIME。"""
        return current_preview_mime()

    def set_fps(self, fps: float) -> float:
        """设置捕获循环目标帧率并返回钳制后的值。"""
        with self._lock:
            self._fps = _clamp_fps(fps)
            return self._fps

    def mjpeg_sleep_s(self) -> float:
        """MJPEG / WS 推送侧等待下一帧的最长阻塞时间（秒），与 FPS 一致。"""
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

    def get_preview_bytes(self) -> bytes:
        """返回当前最新一帧预览二进制（线程安全）。"""
        with self._lock:
            return self._latest

    def get_preview_with_live_fps(self) -> tuple[bytes, float, dict[str, object] | None]:
        """返回当前预览字节、滑动窗口实测 FPS、上一帧页面匹配（预览坐标系）。"""
        with self._lock:
            return self._latest, self._live_fps_unlocked(), self._page_match

    def wait_next_frame(self, timeout_s: float) -> bytes:
        """阻塞直到捕获线程写入新帧或超时，返回当前预览字节。"""
        with self._frame_ready:
            self._frame_ready.wait(timeout=timeout_s)
            return self._latest

    def wait_next_preview_with_live_fps(
        self, timeout_s: float
    ) -> tuple[bytes, float, dict[str, object] | None]:
        """同 `wait_next_frame`，额外返回 FPS 与页面匹配。"""
        with self._frame_ready:
            self._frame_ready.wait(timeout=timeout_s)
            return self._latest, self._live_fps_unlocked(), self._page_match

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
                preview_mime=current_preview_mime(),
                page_match=self._page_match,
            )

    def _live_fps_unlocked(self) -> float:
        """在已持有 `_lock` 下，根据 `_live_fps_times` 估算近期 FPS。"""
        times = self._live_fps_times
        n = len(times)
        if n < 2:
            return float(n)
        dt = times[-1] - times[0]
        if dt <= 1e-9:
            return float(n)
        return (n - 1) / dt

    def _loop(self) -> None:
        """按 FPS 循环：找窗口 → WGC 快照 → 裁切编码 → 写入 `_latest`。"""
        if sys.platform != "win32" or self._wgc is None:
            self._set_frame(_placeholder_preview(), None, 0, 0, None)
            return

        from window_capture import find_game_hwnd, window_title_bar_crop_px

        while not self._stop.is_set():
            t_iter = time.monotonic()
            with self._lock:
                fps = self._fps
            interval = 1.0 / fps
            min_iv = max(1000.0 / fps / 2.0, 8.0)

            hwnd = find_game_hwnd(self._title_regex)
            if hwnd is None:
                self._wgc.ensure_hwnd(None, quality=JPEG_QUALITY, min_interval_ms=min_iv)
                self._set_frame(_placeholder_preview(), None, 0, 0, None)
            else:
                self._wgc.ensure_hwnd(hwnd, quality=JPEG_QUALITY, min_interval_ms=min_iv)
                data, w, h, _ = self._wgc.get_snapshot()
                if data:
                    chop = window_title_bar_crop_px(hwnd)
                    cropped = _decode_and_crop_rgb(data, chop)
                    if cropped is None:
                        self._set_frame(_placeholder_preview(), hwnd, 0, 0, None)
                    else:
                        pm = self._page_matcher.match(cropped, PREVIEW_MAX_WIDTH)
                        out_data, w, h = _encode_cropped_to_preview(cropped)
                        self._set_frame(out_data, hwnd, w, h, pm)
                else:
                    self._set_frame(_placeholder_preview(), hwnd, 0, 0, None)

            delay = interval - (time.monotonic() - t_iter)
            if delay > 0:
                time.sleep(delay)

    def _set_frame(
        self,
        raw: bytes,
        hwnd: int | None,
        w: int,
        h: int,
        page_match: object | None,
    ) -> None:
        """原子更新最新帧、HWND、逻辑尺寸、页面匹配；并记录实测 FPS 样本。"""
        with self._lock:
            self._latest = raw
            self._hwnd = hwnd
            self._size = (w, h)
            self._page_match = _page_match_dict(page_match)
            now = time.monotonic()
            self._live_fps_times.append(now)
            while self._live_fps_times and now - self._live_fps_times[0] > LIVE_FPS_WINDOW_S:
                self._live_fps_times.popleft()
            self._frame_ready.notify_all()
