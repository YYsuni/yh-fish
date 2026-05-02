# -*- coding: utf-8 -*-
"""游戏窗口捕获：WGC 取整窗 JPEG → 裁标题栏与边缘 → 编码为 WebP 预览并按 FPS 更新最新帧。"""

from __future__ import annotations

import io
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

from PIL import Image

from page_template_match import PageMatchResult, PageTemplateMatcher

if sys.platform == "win32":
    from native_stream import WgcHwndStreamer, native_backend_available
else:

    def native_backend_available() -> bool:
        """非 Windows 无 WGC，后端不可用。"""
        return False

    WgcHwndStreamer = None

DEFAULT_TITLE_REGEX = r"^\s*(异环|NTE)\s*$"
# WGC 管线内仍用 JPEG 快照（Windows 捕获）；发给前端的预览固定为 WebP。
WGC_JPEG_QUALITY = 72
# 以下为发给浏览器/WebSocket 的预览图参数；模板匹配在裁剪后的 RGB 上做，不经过这些编码。
WEBP_QUALITY = 78
WEBP_METHOD = 3  # WebP：method 0~6，数值越小编码越快，预览优先低延迟
CROP_MARGIN_LR_PX = 2
CROP_MARGIN_BOTTOM_PX = 2
PREVIEW_MAX_WIDTH = 800  # 先缩小再编码，减体积与编码耗时
FPS_MIN = 1.0
FPS_MAX = 60.0
LIVE_FPS_WINDOW_S = 1.0


def _webp_encode_supported() -> bool:
    """检测当前 Pillow 是否具备 WEBP 编码（依赖 libwebp）。"""
    try:
        Image.new("RGB", (4, 4)).save(io.BytesIO(), format="WEBP")
        return True
    except Exception:
        return False


if not _webp_encode_supported():
    raise RuntimeError("Pillow 无法编码 WEBP（需构建时链接 libwebp）。预览仅支持 WebP，请安装带 WebP 的 Pillow。")

_placeholder_webp_cache: bytes | None = None


def _clamp_fps(v: float) -> float:
    """将 FPS 限制在 [FPS_MIN, FPS_MAX]。"""
    return max(FPS_MIN, min(float(v), FPS_MAX))


def current_preview_mime() -> str:
    """预览二进制帧的 MIME（WS / MJPEG 分片 Content-Type）。"""
    return "image/webp"


def _placeholder_preview() -> bytes:
    """无窗口或捕获失败时的占位图（WebP）。"""
    global _placeholder_webp_cache
    if _placeholder_webp_cache is None:
        img = Image.new("RGB", (640, 360), (248, 250, 252))
        img = _downscale_preview_max_width(img, PREVIEW_MAX_WIDTH)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=70, method=WEBP_METHOD)
        _placeholder_webp_cache = buf.getvalue()
    return _placeholder_webp_cache


def _downscale_preview_max_width(img: Image.Image, max_w: int) -> Image.Image:
    """预览输出：宽度大于 max_w 时按比例缩小（减轻编码与前端解码负担）。"""
    w, h = img.size
    if w <= max_w:
        return img
    new_h = max(1, int(round(h * max_w / w)))
    return img.resize((max_w, new_h), Image.Resampling.BILINEAR)


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
    """将裁剪图按 PREVIEW_MAX_WIDTH 缩小后编码为 WebP；返回 (字节, 逻辑裁剪宽, 逻辑裁剪高)。"""
    cw, ch = cropped.size
    scaled = _downscale_preview_max_width(cropped, PREVIEW_MAX_WIDTH)
    buf = io.BytesIO()
    scaled.save(buf, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    return buf.getvalue(), cw, ch


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
    page_match_threshold: float


def _serialize_page_match(result: PageMatchResult | None) -> dict[str, object] | None:
    """将 `PageMatchResult` 转为可 JSON 序列化的 dict；无匹配时返回 None。"""
    if result is None:
        return None
    return {
        "page_id": result.page_id,
        "page_label": result.label,
        "similarity": float(result.confidence),
        "x": int(result.x),
        "y": int(result.y),
        "w": int(result.w),
        "h": int(result.h),
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

    def set_page_match_threshold(self, threshold: float) -> float:
        """设置 OpenCV 模板匹配下限（0–1）；"""
        return self._page_matcher.set_match_threshold(threshold)

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

    def get_preview_with_live_fps(self) -> tuple[bytes, float, dict[str, object] | None, int, int]:
        """返回预览字节、FPS、页面匹配（裁剪后坐标）；以及同上帧一致的裁剪宽高。"""
        with self._lock:
            return self._snapshot_unlocked()

    def wait_next_frame(self, timeout_s: float) -> bytes:
        """阻塞直到捕获线程写入新帧或超时，返回当前预览字节。"""
        with self._frame_ready:
            self._frame_ready.wait(timeout=timeout_s)
            return self._latest

    def wait_next_preview_with_live_fps(self, timeout_s: float) -> tuple[bytes, float, dict[str, object] | None, int, int]:
        """同 `wait_next_frame`，额外返回 FPS、页面匹配与同帧裁剪尺寸。"""
        with self._frame_ready:
            self._frame_ready.wait(timeout=timeout_s)
            return self._snapshot_unlocked()

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
                page_match_threshold=self._page_matcher.get_match_threshold(),
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

    def _snapshot_unlocked(
        self,
    ) -> tuple[bytes, float, dict[str, object] | None, int, int]:
        cw, ch = self._size
        return self._latest, self._live_fps_unlocked(), self._page_match, cw, ch

    def _loop(self) -> None:
        """按 FPS 循环：找窗口 → WGC 快照 → 裁切编码 → 写入 `_latest`。"""
        if sys.platform != "win32" or self._wgc is None:
            self._set_frame(_placeholder_preview(), None, 0, 0, None)
            return

        from window_capture import find_game_hwnd, window_title_bar_crop_px

        while not self._stop.is_set():
            # 本轮开始时间，用于后面 sleep 补时，尽量贴近目标 FPS。
            t_iter = time.monotonic()
            with self._lock:
                fps = self._fps
            # 目标帧间隔（秒）；WGC 两次抓拍的最小间隔（毫秒），约为半帧，且不低于 8ms。
            interval = 1.0 / fps
            min_iv = max(1000.0 / fps / 2.0, 8.0)

            # 按标题正则找游戏窗口；未找到则占位图 + 释放 WGC 目标。
            hwnd = find_game_hwnd(self._title_regex)
            if hwnd is None:
                self._wgc.ensure_hwnd(None, quality=WGC_JPEG_QUALITY, min_interval_ms=min_iv)
                self._set_frame(_placeholder_preview(), None, 0, 0, None)
            else:
                self._wgc.ensure_hwnd(hwnd, quality=WGC_JPEG_QUALITY, min_interval_ms=min_iv)
                data, w, h, _ = self._wgc.get_snapshot()
                if data:
                    # 去掉标题栏等顶部像素，解码 JPEG 后裁成 RGB，供匹配与预览。
                    chop = window_title_bar_crop_px(hwnd)
                    cropped = _decode_and_crop_rgb(data, chop)
                    if cropped is None:
                        self._set_frame(_placeholder_preview(), hwnd, 0, 0, None)
                    else:
                        pm = self._page_matcher.match(cropped)
                        out_data, w, h = _encode_cropped_to_preview(cropped)
                        self._set_frame(out_data, hwnd, w, h, pm)
                else:
                    # 本帧抓拍失败（空数据）：仍带上 hwnd，前端可知窗口在但画面不可用。
                    self._set_frame(_placeholder_preview(), hwnd, 0, 0, None)

            # 扣除本轮耗时，剩余时间 sleep，避免跑满 CPU。
            delay = interval - (time.monotonic() - t_iter)
            if delay > 0:
                time.sleep(delay)

    def _set_frame(
        self,
        raw: bytes,
        hwnd: int | None,
        w: int,
        h: int,
        page_match: PageMatchResult | None,
    ) -> None:
        """原子更新最新帧、HWND、逻辑尺寸、页面匹配；并记录实测 FPS 样本。"""
        with self._lock:
            self._latest = raw
            self._hwnd = hwnd
            self._size = (w, h)
            self._page_match = _serialize_page_match(page_match)
            now = time.monotonic()
            self._live_fps_times.append(now)
            while self._live_fps_times and now - self._live_fps_times[0] > LIVE_FPS_WINDOW_S:
                self._live_fps_times.popleft()
            self._frame_ready.notify_all()
