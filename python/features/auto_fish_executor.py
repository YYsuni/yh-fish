# -*- coding: utf-8 -*-
"""自动钓鱼执行器：启动后轮询当前页面，按 page_id 调用各页处理函数。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
import tools.game_input as game_input
from tools.page_template_match import (
    DEFAULT_PAGES_JSON,
    match_template_in_precrop_roi,
    match_template_score_in_precrop_roi,
)

_log = logging.getLogger(__name__)

# 自动逻辑状态（与前端 `AutoFishLogicState` 对齐）
LOGIC_FISHING = "fishing"
LOGIC_SELL_FISH = "sell-fish"
LOGIC_BAIT = "bait"
VALID_LOGIC_STATES: frozenset[str] = frozenset({LOGIC_FISHING, LOGIC_SELL_FISH, LOGIC_BAIT})
_LOGIC_LABELS: dict[str, str] = {
    LOGIC_FISHING: "钓鱼",
    LOGIC_SELL_FISH: "卖鱼",
    LOGIC_BAIT: "鱼饵",
}


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
    logic_state: str = LOGIC_FISHING
    apply_logic_state: Callable[[str], None] | None = field(default=None)
    sell_fish_on_no_bait: bool = True  # True：无鱼饵切卖鱼；False：直接鱼饵
    fish_lost_inc: Callable[[], int] | None = field(default=None)  # 累计掉鱼次数 +1，返回新总数


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
        return bool(
            game_input.send_left_click_physical(
                ctx.hwnd, cx, cy, from_precrop=False, hover_dwell_s=0.45, hold_s=0.2
            )
        )

    return bool(game_input.send_left_click(ctx.hwnd, cx, cy))


def _tap_f_cooldown(ctx: TickContext, cooldown_key: str, label: str, cooldown_s: float = 3.0) -> None:
    """按 F 一次，受冷却限制。"""
    if not ctx.cooldown.try_fire(cooldown_key, cooldown_s, ctx.monotonic):
        return
    exec_msg.msg_out(f"{label}：F 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_F)


def _noop_page(ctx: TickContext) -> None:
    _ = ctx


def _page_reeling(ctx: TickContext) -> None:
    """正在溜鱼页面：依据 capture 管线计算的三元组调节 A/D。"""
    if not ctx.cooldown.try_fire("reeling:bar", 0.2, ctx.monotonic):
        return
    triples = ctx.capture.get_last_reeling_bar_triples()
    if triples is None:
        return
    left, right, scale = triples
    if left is None or right is None or scale is None:
        return
    lx, _ly, lw, _lh, _lc = left
    rx, _ry, _rw, _rh, _rc = right
    sx, _sy, sw, _sh, _sc = scale
    left_inner = lx + lw
    right_inner = rx
    if left_inner >= right_inner:
        return
    mid_x = (left_inner + right_inner) / 2.0
    half_span = (right_inner - left_inner) / 2.0
    if half_span <= 0:
        return
    scale_cx = sx + sw // 2
    dev = abs(scale_cx - mid_x)
    if dev < 10:
        return
    hold_max = 0.4
    hold = min(hold_max, hold_max * (dev / 60))
    if scale_cx < mid_x:
        exec_msg.msg_out("溜鱼：D")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_D, hold_between_down_up_s=hold)
    elif scale_cx > mid_x:
        exec_msg.msg_out("溜鱼：A")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_A, hold_between_down_up_s=hold)


def _page_start_fishing(ctx: TickContext) -> None:
    """开始钓鱼页面：卖鱼逻辑点击固定坐标；鱼饵逻辑按 E；否则按 F。"""
    if ctx.logic_state == LOGIC_SELL_FISH:
        if not ctx.cooldown.try_fire("start-fishing:sell-click", 3.0, ctx.monotonic):
            return
        exec_msg.msg_out("开始钓鱼页面：点击仓库")
        game_input.send_left_click_physical(ctx.hwnd, 1010, 707, hover_dwell_s=0.45, hold_s=0.2)
        return
    if ctx.logic_state == LOGIC_BAIT:
        if not ctx.cooldown.try_fire("start-fishing:buy-bait-e", 3.0, ctx.monotonic):
            return
        exec_msg.msg_out("开始钓鱼页面（鱼饵）：E 键按下")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_E)
        return
    _tap_f_cooldown(ctx, "start-fishing", "开始钓鱼页面")


def _page_waiting_for_bite(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "waiting-for-bite", "等待咬钩页面")


def _page_fishing_prep(ctx: TickContext) -> None:
    if ctx.logic_state == LOGIC_FISHING:
        if _click_page_match(ctx, "fishing-prep", "钓鱼准备页面", physical=True):
            time.sleep(1.5)
        return
    if ctx.logic_state == LOGIC_BAIT:
        if not ctx.cooldown.try_fire("fishing-prep:buy-bait-click", 3.0, ctx.monotonic):
            return
        exec_msg.msg_out("钓鱼准备页面：选择鱼饵")
        game_input.send_left_click_physical(ctx.hwnd, 1136, 556, hover_dwell_s=0.45, hold_s=0.2)
        return
    if ctx.apply_logic_state is not None:
        ctx.apply_logic_state(LOGIC_BAIT)


def _page_fishing_end(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("fishing-end", 3.0, ctx.monotonic):
        return
    total = ctx.fish_lost_inc() if ctx.fish_lost_inc else 0
    if ctx.fish_lost_inc:
        exec_msg.msg_out(f"钓鱼结束页面：累计掉鱼 {total} 次，ESC 键按下")
    else:
        exec_msg.msg_out("钓鱼结束页面：ESC 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_ESCAPE)


def _page_empty(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("empty", 3.0, ctx.monotonic):
        return
    exec_msg.msg_out("空页面：ESC 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_ESCAPE)


def _page_fishing_interact(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "fishing-interact", "钓鱼交互页面")


def _page_fish_hooked(ctx: TickContext) -> None:
    _tap_f_cooldown(ctx, "fish-hooked", "上钩页面")


def _page_fish_escaped(ctx: TickContext) -> None:
    _ = ctx


def _page_no_bait(ctx: TickContext) -> None:
    if ctx.logic_state != LOGIC_FISHING:
        return
    if ctx.apply_logic_state is None:
        return
    if ctx.sell_fish_on_no_bait:
        ctx.apply_logic_state(LOGIC_SELL_FISH)
        exec_msg.msg_out("无鱼饵：进入卖鱼逻辑")
    else:
        ctx.apply_logic_state(LOGIC_BAIT)
        exec_msg.msg_out("无鱼饵：进入鱼饵逻辑")


def _page_change_bait(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("change-bait:click", 3.0, ctx.monotonic):
        return
    cropped = ctx.capture.get_last_cropped_rgb_copy()
    region = (747, 507.99, 69, 32)
    s_change = (
        match_template_score_in_precrop_roi(
            cropped,
            DEFAULT_PAGES_JSON.parent / "更换.png",
            region,
        )
        if cropped is not None
        else None
    )
    s_purchase = (
        match_template_score_in_precrop_roi(
            cropped,
            DEFAULT_PAGES_JSON.parent / "购买.png",
            region,
        )
        if cropped is not None
        else None
    )
    c_change = float("-inf") if s_change is None else float(s_change)
    c_pur = float("-inf") if s_purchase is None else float(s_purchase)
    if ctx.apply_logic_state is not None:
        ctx.apply_logic_state(LOGIC_FISHING if c_change > c_pur else LOGIC_BAIT)
    game_input.send_left_click_physical(ctx.hwnd, 761, 516, hover_dwell_s=0.45, hold_s=0.2)


def _page_tip(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("tip:click", 3.0, ctx.monotonic):
        return
    exec_msg.msg_out("提示页面：点击确认")
    game_input.send_left_click_physical(ctx.hwnd, 756, 519, hover_dwell_s=0.45, hold_s=0.2)
    if ctx.apply_logic_state is None:
        return
    if ctx.logic_state == LOGIC_SELL_FISH:
        ctx.apply_logic_state(LOGIC_BAIT)
        exec_msg.msg_out("提示页面：卖鱼流程已完成，切换到鱼饵")
        return
    if ctx.logic_state == LOGIC_BAIT:
        ctx.apply_logic_state(LOGIC_FISHING)
        exec_msg.msg_out("提示页面：鱼饵流程已完成，切回钓鱼")


def _page_tip_no_fish(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("tip-no-fish:click", 3.0, ctx.monotonic):
        return
    game_input.send_key_tap(ctx.hwnd, game_input.VK_ESCAPE)
    exec_msg.msg_out("未获得鱼页面：ESC 关闭")
    if ctx.apply_logic_state is not None:
        ctx.apply_logic_state(LOGIC_BAIT)
        exec_msg.msg_out("未获得鱼页面：切换到鱼饵逻辑")


def _page_shop(ctx: TickContext) -> None:
    """渔具商店页面"""
    if ctx.logic_state == LOGIC_FISHING:
        if not ctx.cooldown.try_fire("shop:buy-bait-esc", 3.0, ctx.monotonic):
            return
        exec_msg.msg_out("渔具商店：ESC 键按下")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_ESCAPE)
        return

    time.sleep(0.5)
    cropped = ctx.capture.get_last_cropped_rgb_copy()
    if cropped is None:
        return
    r = match_template_in_precrop_roi(
        cropped,
        DEFAULT_PAGES_JSON.parent / "万能鱼饵.png",
        (28, 133.99, 424, 328),
        threshold=0.8,
    )
    exec_msg.msg_out(f"渔具商店：匹配鱼饵结果：{r}")
    if r is None:
        return
    if not ctx.cooldown.try_fire("shop:universal-bait-sequence", 4.0, ctx.monotonic):
        return
    x, y, w, h, _conf = r
    cx = x + w // 2
    cy = y + h // 2
    exec_msg.msg_out("渔具商店：点击万能鱼饵")
    game_input.send_left_click_physical(ctx.hwnd, cx, cy, from_precrop=False, hover_dwell_s=0.45, hold_s=0.2)
    time.sleep(0.5)
    exec_msg.msg_out("渔具商店：点击最大数量")
    game_input.send_left_click_physical(ctx.hwnd, 1214, 682, hover_dwell_s=0.45, hold_s=0.2)
    time.sleep(0.4)
    exec_msg.msg_out("渔具商店：点击购买")
    game_input.send_left_click_physical(ctx.hwnd, 1026, 736, hover_dwell_s=0.45, hold_s=0.2)


def _page_market(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("market:click", 3.0, ctx.monotonic):
        return
    exec_msg.msg_out("渔获市场页面：点击归流鱼仓")
    game_input.send_left_click_physical(ctx.hwnd, 100, 327, hover_dwell_s=0.45, hold_s=0.2)


def _page_fish_storage(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("fish-storage:action", 3.0, ctx.monotonic):
        return
    if ctx.logic_state != LOGIC_SELL_FISH:
        exec_msg.msg_out("归流鱼舱页面：ESC 关闭")
        game_input.send_key_tap(ctx.hwnd, game_input.VK_ESCAPE)
        return
    exec_msg.msg_out("归流鱼舱页面：点击卖出")
    game_input.send_left_click_physical(ctx.hwnd, 687, 690, hover_dwell_s=0.45, hold_s=0.2)
    if ctx.apply_logic_state is not None:
        ctx.apply_logic_state(LOGIC_BAIT)


def _page_one_click_sell(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("one-click-sell:click", 3.0, ctx.monotonic):
        return
    exec_msg.msg_out("一键出售页面：点击确认")
    game_input.send_left_click_physical(ctx.hwnd, int(747.5), int(516.22), hover_dwell_s=0.45, hold_s=0.2)


def _page_month_card(ctx: TickContext) -> None:
    if not ctx.cooldown.try_fire("month-card:click", 3.0, ctx.monotonic):
        return
    exec_msg.msg_out("月卡页面：点击领取")
    game_input.send_left_click_physical(ctx.hwnd, 635, 366, hover_dwell_s=0.45, hold_s=0.2)


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
    "change-bait": _page_change_bait,
    "shop": _page_shop,
    "market": _page_market,
    "fish-storage": _page_fish_storage,
    "one-click-sell": _page_one_click_sell,
    "tip": _page_tip,
    "tip-no-fish": _page_tip_no_fish,
    "empty": _page_empty,
    "month-card": _page_month_card,
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
        label = _LOGIC_LABELS.get(logic_state, logic_state)
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
                if page_id:
                    PAGE_HANDLERS.get(page_id, _noop_page)(ctx)
            except Exception:
                _log.exception(
                    "auto-fish page handler failed page_id=%s logic=%s",
                    page_id,
                    logic_effective,
                )

            time.sleep(0.05)

