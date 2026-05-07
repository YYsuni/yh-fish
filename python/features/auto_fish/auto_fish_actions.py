# -*- coding: utf-8 -*-
"""自动钓鱼：页面处理函数共用的输入动作。"""

from __future__ import annotations

import tools.exec_msg as exec_msg
import tools.game_input as game_input

from features.auto_fish.auto_fish_types import TickContext


def click_page_match(
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
        return bool(game_input.send_left_click_physical(ctx.hwnd, cx, cy, from_precrop=False, hover_dwell_s=0.45, hold_s=0.2))

    return bool(game_input.send_left_click(ctx.hwnd, cx, cy))


def tap_f_cooldown(ctx: TickContext, cooldown_key: str, label: str, cooldown_s: float = 3.0) -> None:
    """按 F 一次，受冷却限制。"""
    if not ctx.cooldown.try_fire(cooldown_key, cooldown_s, ctx.monotonic):
        return
    exec_msg.msg_out(f"{label}：F 键按下")
    game_input.send_key_tap(ctx.hwnd, game_input.VK_F)
