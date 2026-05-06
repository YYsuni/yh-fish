# -*- coding: utf-8 -*-
"""店长特供：槽位与单轮 tick 快照（匹配/采集与执行逻辑共用，避免循环依赖）。"""

from __future__ import annotations

from dataclasses import dataclass

CUP_PLATE_ACTION_STATES: frozenset[str] = frozenset(("空", "玻璃杯", "咖啡杯", "玻璃水", "咖啡"))


@dataclass
class ManagerSupplySlotTrack:
    """同一逻辑位置上一类「东西」：按中心像素合并（容差），记录首次出现时间。"""

    cx: int
    cy: int
    label: str
    first_seen: float
    last_seen: float


@dataclass(frozen=True)
class ManagerSupplyDrinkPick:
    """本帧采集到的「最早自动化饮品」槽位（只读）。"""

    label: str
    cx: int
    cy: int


@dataclass(frozen=True)
class ManagerSupplyTickSnapshot:
    """店长特供单轮 tick：仅含采集结果，供 ``execute_manager_supply_tick`` 使用。"""

    monotonic: float
    hwnd: int
    cb_v: str
    cp_v: str
    cb_s: str
    counts: dict[str, int]
    serve_cup_latch: str | None
    earliest_drink: ManagerSupplyDrinkPick | None
