# -*- coding: utf-8 -*-
"""店长执行器：轮询 ``page_match``；店长特供页见 ``manager_supply_page``（采集与执行分离）。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
from features.manager.manager_supply_execute import execute_manager_supply_tick
from features.manager.manager_supply_match import (
    DRINK_AUTOMATION_NAMES,
    MANAGER_SUPPLY_PAGE_ID,
    gather_manager_supply_tick,
    maybe_run_supply_multimatch,
)
from features.manager.manager_tick import CooldownGate, ManagerTickContext

_log = logging.getLogger(__name__)

DEFAULT_POLL_S = 0.05


def _noop_page(ctx: ManagerTickContext) -> None:
    """店长页处理占位：未注册对应 ``page_id`` 时不做任何事。"""
    _ = ctx


MANAGER_PAGE_HANDLERS: dict[str, Callable[[ManagerTickContext], None]] = {}


class ManagerExecutor:
    """与 `CaptureService` 同进程：轮询 `page_match`（店长特供模式下由捕获管线按 images/manager/page.json 填充）。"""

    def __init__(self, capture: CaptureService) -> None:
        """绑定捕获服务并初始化线程与节流门闩。"""
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_page_id: str | None = None
        self._cooldown = CooldownGate()
        self._match_debug: dict[str, object] | None = None

    def supply_match_hit_count(self) -> int:
        """返回最近一次店长特供多模板匹配的命中项数量。"""
        return len(self.supply_match_items_snapshot())

    def supply_match_items_snapshot(self) -> list[dict[str, Any]]:
        """快照当前 ``match_debug`` 中的命中项列表（浅拷贝每项为独立 dict）。"""
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
        """快照完整 ``match_debug``（若没有则为 ``None``）。"""
        with self._lock:
            dbg = self._match_debug
        return dict(dbg) if isinstance(dbg, dict) else None

    def is_running(self) -> bool:
        """店长轮询线程是否仍在运行。"""
        t = self._thread
        return t is not None and t.is_alive()

    def status_dict(self) -> dict[str, object]:
        """导出运行状态：是否在跑、最近一次 ``page_id``、运行中时附带 ``match_debug``。"""
        with self._lock:
            last = self._last_page_id
            dbg = self._match_debug if self.is_running() else None
        return {
            "running": self.is_running(),
            "last_page_id": last,
            "match_debug": dbg,
        }

    def start(self) -> dict[str, object]:
        """启动店长后台线程；若已在运行则返回 ``started: False``。"""
        if self.is_running():
            return {"running": True, "started": False}
        self._stop.clear()
        exec_msg.msg_out("店长特供启动")
        self._thread = threading.Thread(target=self._loop, name="manager", daemon=True)
        self._thread.start()
        return {"running": True, "started": True}

    def stop(self) -> dict[str, object]:
        """请求停止店长线程并清空匹配调试与槽位缓存；可选等待线程退出。"""
        was_running = self.is_running()
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._clear_match_debug_unlocked()
        if was_running:
            exec_msg.msg_out("店长特供停止")
        return {"running": False}

    def _clear_match_debug_unlocked(self) -> None:
        """在已持有 ``self._lock`` 的前提下清空匹配调试。"""
        self._match_debug = None

    def _maybe_run_supply_multimatch(self, now: float, page_id: str | None) -> None:
        """按节流策略在店长特供页跑一次多模板匹配并写回 ``_match_debug`` / 槽位跟踪。"""
        maybe_run_supply_multimatch(self, now, page_id)

    def _loop(self) -> None:
        """店长线程主循环：匹配节流 → 按页采集/执行 → 轮询间隔。"""
        while not self._stop.is_set():
            # 捕获上下文不是店长模式：清空本执行器上的店长状态，短睡后继续
            if self._capture.get_capture_context() != "manager":
                with self._lock:
                    self._last_page_id = None
                    self._clear_match_debug_unlocked()
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
                time.sleep(0.1)
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
                    execute_manager_supply_tick(snap, self._cooldown)
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
