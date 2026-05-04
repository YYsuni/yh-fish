# -*- coding: utf-8 -*-
"""自动钓鱼执行器：启动后轮询当前页面，按 page_id 调用各页处理函数。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
import tools.game_input as game_input
from tools.page_template_match import match_template_in_precrop_roi

_log = logging.getLogger(__name__)


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
    capture: CaptureService
    page_match_threshold: float


def _click_page_match(
    ctx: TickContext,
    cooldown_key: str,
    label: str,
    *,
    physical: bool = False,
    cooldown_s: float = 3.0,
) -> bool:
    """按 page_match 的 x,y,w,h 点击。"""
    pm = ctx.page_match
    try:
        x, y, w, h = (int(pm["x"]), int(pm["y"]), int(pm["w"]), int(pm["h"]))
    except (KeyError, TypeError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    if not ctx.cooldown.try_fire(cooldown_key, cooldown_s, ctx.monotonic):
        return False

    cx = x + w // 2
    cy = y + h // 2
    exec_msg.msg_out(f"{label}：点击匹配区中心 ({cx}, {cy})")
    if physical:
        return bool(game_input.send_left_click_physical(ctx.hwnd, cx, cy, hover_dwell_s=0.45, hold_s=0.2))

    return bool(game_input.send_left_click(ctx.hwnd, cx, cy))


def _tap_f_cooldown(ctx: TickContext, cooldown_key: str, label: str, cooldown_s: float = 3.0) -> None:
    """按 F 一次，受冷却限制。"""
    if not ctx.cooldown.try_fire(cooldown_key, cooldown_s, ctx.monotonic):
        return
    exec_msg.msg_out(f"{label}：F 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_F)


def _noop_page(ctx: TickContext) -> None:
    """未配置页面：不执行。"""
    _ = ctx


def _page_reeling(ctx: TickContext) -> None:
    """正在溜鱼页面：在溜鱼条 ROI 内匹配左/右边缘与刻度，按刻度相对安全区发 A/D。"""
    if not ctx.cooldown.try_fire("reeling:bar", 0.2, ctx.monotonic):
        return
    cropped = ctx.capture.get_last_cropped_rgb_copy()
    if cropped is None:
        return
    img_dir = Path(__file__).resolve().parent / "images" / "auto_fish"
    # 与 pages.json 相同，整窗未裁坐标系 [x, y, w, h]
    reg = (383.74, 94.16, 509.86, 16.58)
    th = 0.8
    left = match_template_in_precrop_roi(cropped, img_dir / "溜鱼条-左边缘.png", reg, threshold=th)
    right = match_template_in_precrop_roi(cropped, img_dir / "溜鱼条-右边缘.png", reg, threshold=th)
    scale = match_template_in_precrop_roi(cropped, img_dir / "溜鱼条-刻度.png", reg, threshold=th)
    if left is None or right is None or scale is None:
        return
    lx, _ly, lw, _lh, _lc = left
    rx, _ry, _rw, _rh, _rc = right
    sx, _sy, sw, _sh, _sc = scale
    left_inner = lx + lw
    right_inner = rx
    if left_inner >= right_inner:
        return
    scale_cx = sx + sw // 2
    hold = 0.2
    if scale_cx < left_inner:
        exec_msg.msg_out("溜鱼：刻度偏左，D")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_D, hold_between_down_up_s=hold)
    elif scale_cx > right_inner:
        exec_msg.msg_out("溜鱼：刻度偏右，A")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_A, hold_between_down_up_s=hold)


def _page_start_fishing(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "start-fishing", "开始钓鱼页面")


def _page_waiting_for_bite(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "waiting-for-bite", "等待咬钩页面")


def _page_fishing_prep(ctx: TickContext) -> None:
    if _click_page_match(ctx, "fishing-prep", "钓鱼准备页面", physical=True):
        time.sleep(1.5)


def _page_fishing_end(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("fishing-end", 3.0, ctx.monotonic):
        return
    exec_msg.msg_out("钓鱼结束页面：ESC 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_ESCAPE)


def _page_fishing_interact(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "fishing-interact", "钓鱼交互页面")


def _page_fish_hooked(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "fish-hooked", "上钩页面")


def _page_fish_escaped(ctx: TickContext) -> None:
    _ = ctx


def _page_no_bait(ctx: TickContext) -> None:
    _ = ctx


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
                time.sleep(0.2)
                continue
            if not isinstance(pm, dict):
                time.sleep(0.05)
                continue

            hwnd = s.hwnd
            now = time.monotonic()
            ctx = TickContext(
                hwnd=hwnd,
                page_match=dict(pm),
                monotonic=now,
                cooldown=self._cooldown,
                capture=self._capture,
                page_match_threshold=float(s.page_match_threshold),
            )
            handler = PAGE_HANDLERS.get(page_id or "", _noop_page)
            try:
                handler(ctx)
            except Exception:
                _log.exception("auto-fish page handler failed page_id=%s", page_id)

            time.sleep(0.05)
