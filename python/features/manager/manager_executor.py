# -*- coding: utf-8 -*-
"""店长执行器：轮询 ``page_match``；店长特供页采集与执行分离。"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
from features.manager.manager_pages import register_manager_pages
from features.manager.manager_supply_execute import execute_manager_supply_tick
from features.manager.manager_supply_match import (
    MANAGER_SUPPLY_PAGE_ID,
    gather_manager_supply_tick,
    maybe_run_supply_multimatch,
    maybe_run_supply_star_only,
)
from features.manager.manager_tick import CooldownGate, ManagerTickContext

_log = logging.getLogger(__name__)

DEFAULT_POLL_S = 0.05


def _noop_page(ctx: ManagerTickContext) -> None:
    """未注册的 ``page_id``：不处理。"""
    _ = ctx


MANAGER_PAGE_HANDLERS: dict[str, Callable[[ManagerTickContext], None]] = {}
register_manager_pages(MANAGER_PAGE_HANDLERS)


class ManagerExecutor:
    """与 ``CaptureService`` 同进程轮询页面；店长模式由捕获管线写入 ``page_match``。"""

    def __init__(self, capture: CaptureService) -> None:
        """绑定捕获服务并初始化线程与节流。"""
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_page_id: str | None = None
        self._cooldown = CooldownGate()
        self._match_debug: dict[str, object] | None = None
        self._direct_knock: bool = True

    def _clear_match_debug_unlocked(self) -> None:
        """在已持有 ``self._lock`` 时清空匹配调试。"""
        self._match_debug = None

    def supply_match_hit_count(self) -> int:
        """最近一次图标多匹配的命中条数。"""
        return len(self.supply_match_items_snapshot())

    def supply_match_items_snapshot(self) -> list[dict[str, Any]]:
        """``match_debug["items"]`` 的浅拷贝列表。"""
        with self._lock:
            dbg = self._match_debug
        if not isinstance(dbg, dict):
            return []
        items = dbg.get("items")
        if not isinstance(items, list):
            return []
        return [dict(el) for el in items if isinstance(el, dict)]

    def supply_match_debug_snapshot(self) -> dict[str, Any] | None:
        """完整 ``match_debug``，无则 ``None``。"""
        with self._lock:
            dbg = self._match_debug
        return dict(dbg) if isinstance(dbg, dict) else None

    def is_running(self) -> bool:
        """后台线程是否存活。"""
        t = self._thread
        return t is not None and t.is_alive()

    def status_dict(self) -> dict[str, object]:
        """运行状态摘要。"""
        with self._lock:
            last = self._last_page_id
            dbg = self._match_debug if self.is_running() else None
            dk = self._direct_knock
        return {
            "running": self.is_running(),
            "last_page_id": last,
            "match_debug": dbg,
            "direct_knock": dk,
        }

    def set_direct_knock(self, enabled: bool) -> dict[str, object]:
        """店长特供页是否跳过图像采集，仅固定坐标连点。"""
        with self._lock:
            self._direct_knock = bool(enabled)
        return self.status_dict()

    def start(self) -> dict[str, object]:
        """启动店长线程。"""
        if self.is_running():
            return {"running": True, "started": False}
        self._stop.clear()
        exec_msg.msg_out("店长特供启动")
        self._thread = threading.Thread(target=self._loop, name="manager", daemon=True)
        self._thread.start()
        return {"running": True, "started": True}

    def stop(self) -> dict[str, object]:
        """停止线程并清空调试缓存。"""
        was_running = self.is_running()
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        self._thread = None
        with self._lock:
            self._match_debug = None
        if was_running:
            exec_msg.msg_out("店长特供停止")
        return {"running": False}

    def _maybe_run_supply_multimatch(self, now: float, page_id: str | None) -> None:
        """店长特供页节流匹配。"""
        maybe_run_supply_multimatch(self, now, page_id)

    def _loop(self) -> None:
        """主循环：非店长上下文则清空状态；特供页采集快照后执行。"""
        while not self._stop.is_set():
            if self._capture.get_capture_context() != "manager":
                with self._lock:
                    self._last_page_id = None
                    self._match_debug = None
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
                time.sleep(0.1)
                continue

            now = time.monotonic()
            hwnd = s.hwnd
            try:
                if page_id == MANAGER_SUPPLY_PAGE_ID:
                    with self._lock:
                        use_direct = self._direct_knock
                    if use_direct:
                        maybe_run_supply_star_only(self, now, page_id)
                        snap = gather_manager_supply_tick(
                            self,
                            monotonic=now,
                            hwnd=hwnd,
                            page_match=dict(pm),
                        )
                        execute_manager_supply_tick(snap, self._cooldown, direct_knock=True)
                    else:
                        self._maybe_run_supply_multimatch(now, page_id)
                        snap = gather_manager_supply_tick(
                            self,
                            monotonic=now,
                            hwnd=hwnd,
                            page_match=dict(pm),
                        )
                        execute_manager_supply_tick(snap, self._cooldown)
                elif page_id:
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
