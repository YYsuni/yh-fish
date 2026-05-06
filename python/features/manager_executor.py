# -*- coding: utf-8 -*-
"""店长特供执行器：对齐 music 执行器结构，轮询页面匹配并维护运行状态。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg

_log = logging.getLogger(__name__)

DEFAULT_POLL_S = 0.05


class CooldownGate:
    """按 key 记录上次触发时间，用于防抖/节流。"""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def try_fire(self, key: str, min_interval_s: float, now: float) -> bool:
        last = self._last.get(key, 0.0)
        if now - last >= min_interval_s:
            self._last[key] = now
            return True
        return False


@dataclass
class ManagerTickContext:
    hwnd: int
    page_match: dict[str, object]
    monotonic: float
    cooldown: CooldownGate
    capture: CaptureService


def _noop_page(ctx: ManagerTickContext) -> None:
    _ = ctx


def _page_manager_supply(ctx: ManagerTickContext) -> None:
    """店长特供页面：当前先只节流输出，后续可加自动操作。"""
    if not ctx.cooldown.try_fire("manager:manager-supply:log", 2.0, ctx.monotonic):
        return
    exec_msg.msg_out("店长特供页面：已识别")


MANAGER_PAGE_HANDLERS: dict[str, Callable[[ManagerTickContext], None]] = {
    "manager-supply": _page_manager_supply,
}


class ManagerExecutor:
    """与 `CaptureService` 同进程：轮询 `page_match`（店长特供模式下由捕获管线按 images/manager/page.json 填充）。"""

    def __init__(self, capture: CaptureService) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_page_id: str | None = None
        self._cooldown = CooldownGate()

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
        if was_running:
            exec_msg.msg_out("店长特供停止")
        return {"running": False}

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._capture.get_capture_context() != "manager":
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
            ctx = ManagerTickContext(
                hwnd=hwnd,
                page_match=dict(pm),
                monotonic=now,
                cooldown=self._cooldown,
                capture=self._capture,
            )
            try:
                if page_id:
                    MANAGER_PAGE_HANDLERS.get(page_id, _noop_page)(ctx)
            except Exception:
                _log.exception("manager page handler failed page_id=%s", page_id)

            time.sleep(DEFAULT_POLL_S)

