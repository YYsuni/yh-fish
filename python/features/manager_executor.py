# -*- coding: utf-8 -*-
"""店长执行器：轮询 ``page_match``；店长特供页见 ``manager_supply_page``（采集与执行分离）。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
from features.manager_supply_execute import execute_manager_supply_tick
from features.manager_supply_page import (
    DRINK_AUTOMATION_NAMES,
    DRINK_SUPPLY_SLOT_TOL_PX,
    MANAGER_SUPPLY_PAGE_ID,
    gather_manager_supply_tick,
    maybe_run_supply_multimatch,
)
from features.manager_supply_snapshot import ManagerSupplySlotTrack
from features.manager_tick import CooldownGate, ManagerTickContext

_log = logging.getLogger(__name__)

DEFAULT_POLL_S = 0.05


def _noop_page(ctx: ManagerTickContext) -> None:
    _ = ctx


MANAGER_PAGE_HANDLERS: dict[str, Callable[[ManagerTickContext], None]] = {}


class ManagerExecutor:
    """与 `CaptureService` 同进程：轮询 `page_match`（店长特供模式下由捕获管线按 images/manager/page.json 填充）。"""

    def __init__(self, capture: CaptureService) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_page_id: str | None = None
        self._cooldown = CooldownGate()
        self._match_debug: dict[str, object] | None = None
        self._cup_plate_tracks: list[ManagerSupplySlotTrack] = []
        self._drink_tracks: list[ManagerSupplySlotTrack] = []
        self._serve_cup_latch: str | None = None

    def supply_match_hit_count(self) -> int:
        return len(self.supply_match_items_snapshot())

    def supply_match_items_snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            dbg = self._match_debug
        if not isinstance(dbg, dict):
            return []
        items = dbg.get("items")
        if not isinstance(items, list):
            return []
        out: list[dict[str, Any]] = []
        for el in items:
            if isinstance(el, dict):
                out.append(dict(el))
        return out

    def supply_match_debug_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            dbg = self._match_debug
        return dict(dbg) if isinstance(dbg, dict) else None

    def peek_earliest_automation_drink(self) -> ManagerSupplySlotTrack | None:
        with self._lock:
            cands = [t for t in self._drink_tracks if t.label in DRINK_AUTOMATION_NAMES]
            if not cands:
                return None
            return min(cands, key=lambda t: t.first_seen)

    def discard_drink_track(self, slot: ManagerSupplySlotTrack) -> None:
        with self._lock:
            self._drink_tracks = [
                x
                for x in self._drink_tracks
                if not (x.label == slot.label and abs(x.cx - slot.cx) <= DRINK_SUPPLY_SLOT_TOL_PX and abs(x.cy - slot.cy) <= DRINK_SUPPLY_SLOT_TOL_PX)
            ]

    def serve_cup_latch_get(self) -> str | None:
        with self._lock:
            return self._serve_cup_latch

    def serve_cup_latch_replace(self, cp_v: str | None) -> None:
        with self._lock:
            self._serve_cup_latch = cp_v

    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def status_dict(self) -> dict[str, object]:
        with self._lock:
            last = self._last_page_id
            dbg = self._match_debug if self.is_running() else None
        return {
            "running": self.is_running(),
            "last_page_id": last,
            "match_debug": dbg,
        }

    def start(self) -> dict[str, object]:
        if self.is_running():
            return {"running": True, "started": False}
        self._stop.clear()
        exec_msg.msg_out("店长特供启动")
        self._thread = threading.Thread(target=self._loop, name="manager", daemon=True)
        self._thread.start()
        return {"running": True, "started": True}

    def stop(self) -> dict[str, object]:
        was_running = self.is_running()
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._clear_match_debug_unlocked()
            self._cup_plate_tracks.clear()
            self._drink_tracks.clear()
        if was_running:
            exec_msg.msg_out("店长特供停止")
        return {"running": False}

    def _clear_match_debug_unlocked(self) -> None:
        self._match_debug = None
        self._serve_cup_latch = None

    def _maybe_run_supply_multimatch(self, now: float, page_id: str | None) -> None:
        maybe_run_supply_multimatch(self, now, page_id)

    def _loop(self) -> None:
        """店长线程主循环：匹配节流 → 按页采集/执行 → 轮询间隔。"""
        while not self._stop.is_set():
            # 捕获上下文不是店长模式：清空本执行器上的店长状态，短睡后继续
            if self._capture.get_capture_context() != "manager":
                with self._lock:
                    self._last_page_id = None
                    self._clear_match_debug_unlocked()
                    self._cup_plate_tracks.clear()
                    self._drink_tracks.clear()
                time.sleep(0.05)
                continue

            # 当前捕获状态与页面识别结果（来自 capture 管线）
            s = self._capture.get_status()
            pm = s.page_match
            page_id: str | None = None
            if isinstance(pm, dict):
                pid = pm.get("page_id")
                if isinstance(pid, str):
                    page_id = pid
            with self._lock:
                self._last_page_id = page_id

            # 窗口无效或无 page_match：不跑店长逻辑
            if not s.ok or s.hwnd is None:
                time.sleep(0.2)
                continue
            if not isinstance(pm, dict):
                time.sleep(0.05)
                continue

            # 店长特供页：节流内更新 match_debug / 饮品与杯子盘槽位
            now = time.monotonic()
            self._maybe_run_supply_multimatch(now, page_id)

            hwnd = s.hwnd
            try:
                if page_id == MANAGER_SUPPLY_PAGE_ID:
                    # 先采集本帧快照，再按快照执行（不混读 match）
                    snap = gather_manager_supply_tick(
                        self,
                        monotonic=now,
                        hwnd=hwnd,
                        page_match=dict(pm),
                    )
                    execute_manager_supply_tick(snap, self, self._cooldown)
                elif page_id:
                    # 其它店长子页（预留）：走通用 tick 上下文
                    ctx = ManagerTickContext(
                        hwnd=hwnd,
                        page_match=dict(pm),
                        monotonic=now,
                        cooldown=self._cooldown,
                        capture=self._capture,
                        executor=self,
                    )
                    MANAGER_PAGE_HANDLERS.get(page_id, _noop_page)(ctx)
            except Exception:
                _log.exception("manager page handler failed page_id=%s", page_id)

            time.sleep(DEFAULT_POLL_S)
