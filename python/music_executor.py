# -*- coding: utf-8 -*-
"""超强音执行器：按 `images/music/page.json` 识别当前页，再执行各页处理函数（与自动钓鱼结构类似）。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
import tools.game_input as game_input

_log = logging.getLogger(__name__)


class CooldownGate:
    """按 key 记录上次触发时间，用于极短防抖（避免阈值附近抖动连发）。"""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def try_fire(self, key: str, min_interval_s: float, now: float) -> bool:
        last = self._last.get(key, 0.0)
        if now - last >= min_interval_s:
            self._last[key] = now
            return True
        return False


class DrumEdgeTracker:
    """每槽保留上一帧相似度；仅当「上一帧 ≥ 阈值且本帧 < 阈值」时记为一次下跳（一击一记）。"""

    def __init__(self) -> None:
        self._prev: dict[str, float | None] = {}

    def clear(self) -> None:
        self._prev.clear()

    def crossed_below(self, slot_key: str, sim: float, th: float) -> bool:
        prev = self._prev.get(slot_key)
        self._prev[slot_key] = sim
        if prev is None:
            return False
        return prev >= th and sim < th


# 阈值附近同一拍下多次 PostMessage 的间隔下限（秒），不是「音符间隔」锁
DRUM_DEBOUNCE_S = 0.028
# 敲鼓页轮询间隔（秒），略快于原 50ms，减少错过短暂下跳
DRUM_POLL_S = 0.012
DEFAULT_POLL_S = 0.05


@dataclass
class MusicTickContext:
    hwnd: int
    page_match: dict[str, object]
    monotonic: float
    cooldown: CooldownGate
    drum_edge: DrumEdgeTracker
    capture: CaptureService


def _noop_page(ctx: MusicTickContext) -> None:
    _ = ctx


def _page_drum(ctx: MusicTickContext) -> None:
    """敲鼓页面：相似度从下穿上阈值（下降沿）发键；持续低于阈值不会连发，避免误触与漏判混淆。"""
    st = ctx.capture.get_status()
    th = float(st.page_match_threshold)
    mdd = st.music_drum_debug
    if not isinstance(mdd, dict):
        return
    raw_items = mdd.get("items")
    if not isinstance(raw_items, list):
        return

    for it in raw_items:
        if not isinstance(it, dict):
            continue
        sim = it.get("similarity")
        if sim is None:
            continue
        try:
            sval = float(sim)
        except (TypeError, ValueError):
            continue

        kid = str(it.get("key", ""))
        if not kid:
            continue
        if not ctx.drum_edge.crossed_below(kid, sval, th):
            continue
        if not ctx.cooldown.try_fire(f"music:drum:{kid}", DRUM_DEBOUNCE_S, ctx.monotonic):
            continue

        vk_raw = it.get("vk")
        try:
            vk_code = int(vk_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue

        label = str(it.get("label", "?"))
        exec_msg.msg_out(f"敲鼓 [{label}]：沿 ↓ sim {sval:.2f} < {th:.2f}")
        game_input.send_key_tap(ctx.hwnd, vk_code)


MUSIC_PAGE_HANDLERS: dict[str, Callable[[MusicTickContext], None]] = {
    "drum": _page_drum,
}


class MusicExecutor:
    """与 `CaptureService` 同进程：轮询 `page_match`（超强音模式下由捕获管线按 music/page.json 填充）。"""

    def __init__(self, capture: CaptureService) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cooldown = CooldownGate()
        self._drum_edge = DrumEdgeTracker()
        self._last_page_id: str | None = None

    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def status_dict(self) -> dict[str, object]:
        with self._lock:
            last = self._last_page_id
        return {
            "running": self.is_running(),
            "last_page_id": last,
        }

    def start(self) -> dict[str, object]:
        if self.is_running():
            return {"running": True, "started": False}
        self._stop.clear()
        exec_msg.msg_out("超强音启动")
        self._thread = threading.Thread(target=self._loop, name="music", daemon=True)
        self._thread.start()
        return {"running": True, "started": True}

    def stop(self) -> dict[str, object]:
        was_running = self.is_running()
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        self._thread = None
        if was_running:
            exec_msg.msg_out("超强音停止")
        return {"running": False}

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._capture.get_capture_context() != "music":
                with self._lock:
                    self._last_page_id = None
                time.sleep(0.05)
                continue

            s = self._capture.get_status()
            pm = s.page_match
            page_id: str | None = None
            if isinstance(pm, dict):
                pid = pm.get("page_id")
                if isinstance(pid, str):
                    page_id = pid
            with self._lock:
                self._last_page_id = page_id

            if not s.ok or s.hwnd is None:
                time.sleep(0.2)
                continue
            if not isinstance(pm, dict):
                time.sleep(0.05)
                continue

            if page_id != "drum":
                self._drum_edge.clear()

            hwnd = s.hwnd
            now = time.monotonic()
            ctx = MusicTickContext(
                hwnd=hwnd,
                page_match=dict(pm),
                monotonic=now,
                cooldown=self._cooldown,
                drum_edge=self._drum_edge,
                capture=self._capture,
            )
            try:
                if page_id:
                    MUSIC_PAGE_HANDLERS.get(page_id, _noop_page)(ctx)
            except Exception:
                _log.exception("music page handler failed page_id=%s", page_id)

            time.sleep(DRUM_POLL_S if page_id == "drum" else DEFAULT_POLL_S)
