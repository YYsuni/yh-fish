# -*- coding: utf-8 -*-
"""自动钓鱼执行器：启动后轮询当前页面，按 page_id 调用各页处理函数。"""

from __future__ import annotations

import logging
import threading
import time

from capture_service import CaptureService

import tools.exec_msg as exec_msg
from features.auto_fish.auto_fish_pages import get_page_handler
from features.auto_fish.auto_fish_types import (
    CooldownGate,
    LOGIC_FISHING,
    LOGIC_LABELS_ZH,
    VALID_LOGIC_STATES,
    TickContext,
)

_log = logging.getLogger(__name__)


class AutoFishExecutor:
    """与 `CaptureService` 同进程：单独线程轮询页面并执行 `PAGE_HANDLERS`。"""

    def __init__(self, capture: CaptureService) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cooldown = CooldownGate()
        self._last_page_id: str | None = None
        self._logic_state: str = LOGIC_FISHING
        self._sell_fish_on_no_bait: bool = True
        self._fish_lost_total: int = 0

    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def status_dict(self) -> dict[str, object]:
        with self._lock:
            last = self._last_page_id
            logic = self._logic_state
            sell_on_no = self._sell_fish_on_no_bait
            lost = self._fish_lost_total
        return {
            "running": self.is_running(),
            "last_page_id": last,
            "logic_state": logic,
            "sell_fish_on_no_bait": sell_on_no,
            "fish_lost_total": lost,
        }

    def _apply_logic_state(self, logic_state: str) -> None:
        if logic_state not in VALID_LOGIC_STATES:
            return
        with self._lock:
            self._logic_state = logic_state

    def _increment_fish_lost(self) -> int:
        with self._lock:
            self._fish_lost_total += 1
            return self._fish_lost_total

    def set_logic_state(self, logic_state: str) -> dict[str, object]:
        if logic_state not in VALID_LOGIC_STATES:
            raise ValueError(f"无效 logic_state: {logic_state!r}")
        label = LOGIC_LABELS_ZH.get(logic_state, logic_state)
        self._apply_logic_state(logic_state)
        exec_msg.msg_out(f"逻辑切换为：{label}")
        return self.status_dict()

    def set_sell_fish_on_no_bait(self, enabled: bool) -> dict[str, object]:
        with self._lock:
            self._sell_fish_on_no_bait = bool(enabled)
        return self.status_dict()

    def start(self) -> dict[str, object]:
        if self.is_running():
            return {"running": True, "started": False}
        self._stop.clear()
        exec_msg.msg_out("自动钓鱼启动")
        self._thread = threading.Thread(target=self._loop, name="auto-fish", daemon=True)
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
            exec_msg.msg_out("自动钓鱼停止")
        return {"running": False}

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._capture.get_capture_context() != "fish":
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

            hwnd = s.hwnd
            now = time.monotonic()

            with self._lock:
                logic_effective = self._logic_state
                sell_on_no_bait = self._sell_fish_on_no_bait

            ctx = TickContext(
                hwnd=hwnd,
                page_match=dict(pm),
                monotonic=now,
                cooldown=self._cooldown,
                capture=self._capture,
                page_match_threshold=float(s.page_match_threshold),
                logic_state=logic_effective,
                apply_logic_state=self._apply_logic_state,
                sell_fish_on_no_bait=sell_on_no_bait,
                fish_lost_inc=self._increment_fish_lost,
            )
            try:
                get_page_handler(page_id)(ctx)
            except Exception:
                _log.exception(
                    "auto-fish page handler failed page_id=%s logic=%s",
                    page_id,
                    logic_effective,
                )

            time.sleep(0.05)
