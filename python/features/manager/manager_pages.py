# -*- coding: utf-8 -*-
"""店长页面逻辑（pages）。"""

from __future__ import annotations

from typing import Callable

import tools.game_input as game_input

from features.manager.manager_tick import ManagerTickContext


def execute_skip_guide(ctx: ManagerTickContext) -> None:
    """引导页面：点击跳过引导。"""
    if not ctx.cooldown.try_fire("manager:skip-guide-click", 1, ctx.monotonic):
        return
    game_input.send_left_click_physical(ctx.hwnd, 87, 88, hover_dwell_s=0.1, hold_s=0.1)


PAGE_HANDLERS: dict[str, Callable[[ManagerTickContext], None]] = {
    "skip-guide": execute_skip_guide,
}


def register_manager_pages(handlers: dict[str, Callable[[ManagerTickContext], None]]) -> None:
    handlers.update(PAGE_HANDLERS)
