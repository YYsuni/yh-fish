# -*- coding: utf-8 -*-
"""店长线程单次 tick 上下文与节流（与具体页面逻辑解耦）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    capture: Any
    executor: Any
