# -*- coding: utf-8 -*-
"""店长特供：根据 tick 快照执行日志与物理点击。"""

from __future__ import annotations

import logging
from typing import Any

import tools.exec_msg as exec_msg
import tools.game_input as game_input

from features.manager_supply_snapshot import (
    CUP_PLATE_ACTION_STATES,
    ManagerSupplySlotTrack,
    ManagerSupplyTickSnapshot,
)
from features.manager_tick import CooldownGate

_log = logging.getLogger(__name__)


def _format_supply_counts_zh(counts: dict[str, int]) -> str:
    if not counts:
        return "无有效分类"
    return "，".join(f"{k} {v} 个" for k, v in counts.items())


def _serve_precrop_xy_for_drink(drink: str) -> tuple[tuple[int, int], tuple[int, int]]:
    if drink == "烤椰拿铁":
        return (828, 556), (909, 460)
    return (1206, 567), (1023, 459)


def _manager_serve_click_precrop(hwnd: int, x: int, y: int) -> None:
    game_input.send_left_click_physical(hwnd, x, y, hover_dwell_s=0.1, hold_s=0.2)


def execute_manager_supply_tick(
    snapshot: ManagerSupplyTickSnapshot,
    executor: Any,
    cooldown: CooldownGate,
) -> None:
    """仅根据 ``snapshot`` 写日志并发送输入（不再读 match_debug / 槽位）。"""
    if cooldown.try_fire("manager:manager-supply:log", 2.0, snapshot.monotonic):
        exec_msg.msg_out(f"店长特供页面：{_format_supply_counts_zh(snapshot.counts)}；" f"咖啡后台={snapshot.cb_v}（{snapshot.cb_s}）；杯子盘={snapshot.cp_v}")

    cp_v = snapshot.cp_v
    if cp_v in CUP_PLATE_ACTION_STATES:
        if snapshot.serve_cup_latch != cp_v and snapshot.earliest_drink is not None:
            pick = snapshot.earliest_drink
            (x1, y1), (x2, y2) = _serve_precrop_xy_for_drink(pick.label)
            slot_for_discard = ManagerSupplySlotTrack(pick.cx, pick.cy, pick.label, 0.0, 0.0)
            try:
                if cp_v == "空":
                    _manager_serve_click_precrop(snapshot.hwnd, x1, y1)
                elif cp_v in ("玻璃杯", "咖啡杯"):
                    _manager_serve_click_precrop(snapshot.hwnd, 1180, 702)
                else:
                    _manager_serve_click_precrop(snapshot.hwnd, x2, y2)
                    executor.discard_drink_track(slot_for_discard)
            except Exception:
                _log.exception("manager serve drink click failed")
                return
            executor.serve_cup_latch_replace(cp_v)

    if snapshot.cb_v == "空":
        if cooldown.try_fire("manager:coffee-back-empty-click", 3.0, snapshot.monotonic):
            try:
                game_input.send_left_click_physical(
                    snapshot.hwnd,
                    1030,
                    702,
                    hover_dwell_s=0.1,
                    hold_s=0.2,
                )
            except Exception:
                _log.exception("manager coffee-back empty physical click failed")
