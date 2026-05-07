# -*- coding: utf-8 -*-
"""店长特供：根据 tick 快照执行日志与物理点击。"""

from __future__ import annotations

import logging
from typing import Any

import tools.exec_msg as exec_msg
import tools.game_input as game_input

from features.manager.manager_tick import (
    CooldownGate,
    ManagerSupplyTickSnapshot,
)

_log = logging.getLogger(__name__)


def _format_supply_counts_zh(counts: dict[str, int]) -> str:
    if not counts:
        return "无有效分类"
    return "，".join(f"{k} {v} 个" for k, v in counts.items())


def _pick_top_label(counts: dict[str, int]) -> str | None:
    """从 counts 中选出数量最多的 label（忽略 <=0 的值；并列取首次出现者）。"""
    pick_label: str | None = None
    best_n = 0
    for k, v in counts.items():
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > best_n:
            best_n = n
            pick_label = str(k)
    return pick_label


def execute_manager_supply_tick(
    snapshot: ManagerSupplyTickSnapshot,
    cooldown: CooldownGate,
) -> None:

    def click_physical(
        x: int,
        y: int,
    ) -> None:
        if cooldown.try_fire(f"click:{x},{y}", 0.5, snapshot.monotonic):
            game_input.send_left_click_physical(snapshot.hwnd, x, y, hover_dwell_s=0.1, hold_s=0.1)

    if cooldown.try_fire("manager:manager-supply:log", 2.0, snapshot.monotonic):
        exec_msg.msg_out(
            f"店长特供页面：{_format_supply_counts_zh(snapshot.counts)}；"
            f"分数={len(snapshot.score)}；"
            # f"咖啡后台={snapshot.cb_v}；"
            # f"咖啡机={snapshot.coffee_machine_status}；"
            # f"杯子盘={snapshot.cp_v}"
        )

    cp_v = snapshot.cp_v
    pick_label = _pick_top_label(snapshot.counts)

    if cp_v == "空" and pick_label is not None:
        if pick_label == "烤椰拿铁":
            click_physical(828, 556)
        else:
            click_physical(1206, 567)
    elif cp_v in ("玻璃杯", "咖啡杯"):
        click_physical(1180, 702)
    elif cp_v == "咖啡":
        click_physical(909, 460)
    elif cp_v == "玻璃水":
        click_physical(1023, 459)

    if snapshot.cb_v == "空" and snapshot.coffee_machine_status == "空闲" and cooldown.try_fire("manager:coffee-back-empty-click", 0.5, snapshot.monotonic):
        click_physical(1030, 702)

    if snapshot.score is not None and len(snapshot.score) > 0:
        click_physical(30, 72)
