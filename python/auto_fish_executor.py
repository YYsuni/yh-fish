# -*- coding: utf-8 -*-
"""自动钓鱼执行器：启动后轮询当前页面，按 page_id 调用各页处理函数。

各页具体按键在下方 `PAGE_HANDLERS` 中补充；冷却请用 `TickContext.cooldown`。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from capture_service import CaptureService

import tools.exec_msg as exec_msg
import tools.game_input as game_input

_log = logging.getLogger(__name__)

# 各页冷却 key（互不共用；间隔 `SINGLE_ACTION_COOLDOWN_S`）
_F_REELING_KEY = "reeling:f"
_F_START_FISHING_KEY = "start-fishing:f"
_F_WAITING_FOR_BITE_KEY = "waiting-for-bite:f"
_F_FISHING_END_KEY = "fishing-end:f"
_F_FISHING_INTERACT_KEY = "fishing-interact:f"
_F_FISH_HOOKED_KEY = "fish-hooked:f"
_F_FISH_ESCAPED_KEY = "fish-escaped:f"
_F_NO_BAIT_KEY = "no-bait:f"

_F_FISHING_PREP_CLICK_KEY = "fishing-prep:click"
_FISHING_PREP_CLICK_OFFSET_XY = (15, 15)
FISHING_PREP_AFTER_CLICK_SETTLE_S = 1.5
_FISHING_PREP_USE_PHYSICAL_CLICK = True

SINGLE_ACTION_COOLDOWN_S = 3.0
TICK_INTERVAL_S = 0.05
IDLE_WHEN_NO_WINDOW_S = 0.2


class CooldownGate:
    """按任意字符串 key 记录上次触发时间，`try_fire` 超过间隔才返回 True 并刷新时间。"""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def try_fire(self, key: str, min_interval_s: float, now: float) -> bool:
        last = self._last.get(key, 0.0)
        if now - last >= min_interval_s:
            self._last[key] = now
            return True
        return False


@dataclass
class TickContext:
    """每一拍传给页面处理函数的上下文。"""

    hwnd: int
    page_match: dict[str, object]
    monotonic: float
    cooldown: CooldownGate


def _click_page_match(
    ctx: TickContext,
    cooldown_key: str,
    label: str,
    *,
    from_topleft: tuple[int, int] | None = None,
    physical: bool = False,
) -> bool:
    """按 page_match 的 x,y,w,h 点击。`from_topleft` 为相对匹配左上角的偏移；`None` 为矩形中心。"""
    pm = ctx.page_match
    try:
        x, y, w, h = (int(pm["x"]), int(pm["y"]), int(pm["w"]), int(pm["h"]))
    except (KeyError, TypeError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    if not ctx.cooldown.try_fire(cooldown_key, SINGLE_ACTION_COOLDOWN_S, ctx.monotonic):
        return False
    if from_topleft is not None:
        dx, dy = (int(from_topleft[0]), int(from_topleft[1]))
        cx = max(x, min(x + w - 1, x + dx))
        cy = max(y, min(y + h - 1, y + dy))
        exec_msg.msg_out(f"{label}：点击匹配区左上+偏移 ({cx}, {cy})")
    else:
        cx = x + w // 2
        cy = y + h // 2
        exec_msg.msg_out(f"{label}：点击匹配区中心 ({cx}, {cy})")
    if physical:
        return bool(game_input.send_left_click_physical(ctx.hwnd, cx, cy))
    return bool(game_input.send_left_click(ctx.hwnd, cx, cy))


def _tap_f_cooldown(ctx: TickContext, cooldown_key: str, label: str) -> None:
    """按 F 一次，受 `cooldown_key` 与 `SINGLE_ACTION_COOLDOWN_S` 限制。"""
    if not ctx.cooldown.try_fire(cooldown_key, SINGLE_ACTION_COOLDOWN_S, ctx.monotonic):
        return
    exec_msg.msg_out(f"{label}：F 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_F)


def _noop_page(ctx: TickContext) -> None:
    """未配置页面：不执行。"""
    _ = ctx


def _page_reeling(ctx: TickContext) -> None:
    """正在溜鱼页面"""
    _ = ctx


def _page_start_fishing(ctx: TickContext) -> None:
    """开始钓鱼页面"""
    _tap_f_cooldown(ctx, _F_START_FISHING_KEY, "开始钓鱼页面")


def _page_waiting_for_bite(ctx: TickContext) -> None:
    """等待咬钩页面"""
    _tap_f_cooldown(ctx, _F_WAITING_FOR_BITE_KEY, "等待咬钩页面")


def _page_fishing_prep(ctx: TickContext) -> None:
    """钓鱼准备页面"""
    if _click_page_match(
        ctx,
        _F_FISHING_PREP_CLICK_KEY,
        "钓鱼准备页面",
        from_topleft=_FISHING_PREP_CLICK_OFFSET_XY,
        physical=_FISHING_PREP_USE_PHYSICAL_CLICK,
    ):
        time.sleep(FISHING_PREP_AFTER_CLICK_SETTLE_S)


def _page_fishing_end(ctx: TickContext) -> None:
    """钓鱼结束页面"""
    _ = ctx


def _page_fishing_interact(ctx: TickContext) -> None:
    """钓鱼交互页面"""
    _tap_f_cooldown(ctx, _F_FISHING_INTERACT_KEY, "钓鱼交互页面")


def _page_fish_hooked(ctx: TickContext) -> None:
    """上钩页面"""
    _tap_f_cooldown(ctx, _F_FISH_HOOKED_KEY, "上钩页面")


def _page_fish_escaped(ctx: TickContext) -> None:
    """鱼儿溜走页面"""
    _ = ctx


def _page_no_bait(ctx: TickContext) -> None:
    """无鱼饵状态"""
    _ = ctx


# pages.json 中 `id` → 处理函数（在此为各页补充具体命令）
PAGE_HANDLERS: dict[str, Callable[[TickContext], None]] = {
    "reeling": _page_reeling,
    "start-fishing": _page_start_fishing,
    "waiting-for-bite": _page_waiting_for_bite,
    "fishing-prep": _page_fishing_prep,
    "fishing-end": _page_fishing_end,
    "fishing-interact": _page_fishing_interact,
    "fish-hooked": _page_fish_hooked,
    "fish-escaped": _page_fish_escaped,
    "no-bait": _page_no_bait,
}


class AutoFishExecutor:
    """与 `CaptureService` 同进程：单独线程轮询页面并执行 `PAGE_HANDLERS`。"""

    def __init__(self, capture: CaptureService) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cooldown = CooldownGate()
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
        self._thread = threading.Thread(target=self._loop, name="auto-fish", daemon=True)
        self._thread.start()
        exec_msg.msg_out("自动钓鱼启动")
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
                time.sleep(IDLE_WHEN_NO_WINDOW_S)
                continue
            if not isinstance(pm, dict):
                time.sleep(TICK_INTERVAL_S)
                continue

            hwnd = s.hwnd
            now = time.monotonic()
            ctx = TickContext(hwnd=hwnd, page_match=dict(pm), monotonic=now, cooldown=self._cooldown)
            handler = PAGE_HANDLERS.get(page_id or "", _noop_page)
            try:
                handler(ctx)
            except Exception:
                _log.exception("auto-fish page handler failed page_id=%s", page_id)

            time.sleep(TICK_INTERVAL_S)
