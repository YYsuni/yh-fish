# -*- coding: utf-8 -*-
"""自动钓鱼：状态/上下文/节流等基础类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from capture_service import CaptureService

# 自动逻辑状态（与前端 `AutoFishLogicState` 对齐）
LOGIC_FISHING = "fishing"
LOGIC_SELL_FISH = "sell-fish"
LOGIC_BAIT = "bait"
VALID_LOGIC_STATES: frozenset[str] = frozenset({LOGIC_FISHING, LOGIC_SELL_FISH, LOGIC_BAIT})

LOGIC_LABELS_ZH: dict[str, str] = {
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
