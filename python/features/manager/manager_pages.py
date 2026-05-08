# -*- coding: utf-8 -*-
"""店长页面逻辑（pages）。"""

from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Callable

import tools.game_input as game_input

from features.page_match_paths import MANAGER_PAGES_JSON
from features.manager.manager_tick import ManagerTickContext
from tools.page_template_match import match_template_in_precrop_roi


def execute_skip_guide(ctx: ManagerTickContext) -> None:
    """引导页面：点击跳过引导。"""
    if not ctx.cooldown.try_fire("manager:skip-guide-click", 1, ctx.monotonic):
        return
    game_input.send_left_click_physical(ctx.hwnd, 87, 88, hover_dwell_s=0.1, hold_s=0.1)


def execute_manager_level(ctx: ManagerTickContext) -> None:
    """特供选关页面：点击选关。"""
    if not ctx.executor.is_auto_select_level():
        return
    cropped = ctx.capture.get_last_cropped_rgb_copy()
    if cropped is None:
        return

    template_path: Path = MANAGER_PAGES_JSON.parent / "最新关卡.png"
    # 整窗未裁坐标系 ROI [x, y, w, h]
    region_precrop = (63.0, 144.0, 107.0, 586.0)
    th = float(ctx.capture.get_status().page_match_threshold)
    hit = match_template_in_precrop_roi(
        cropped,
        template_path,
        region_precrop,
        threshold=th,
    )

    # 匹配到就点中心
    if hit is not None:
        if not ctx.cooldown.try_fire("manager:level:click", 3, ctx.monotonic):
            return
        x, y, w, h, _conf = hit
        cx = int(round(x + w / 2.0))
        cy = int(round(y + h / 2.0))
        game_input.send_left_click_physical(
            ctx.hwnd,
            cx,
            cy,
            from_precrop=False,  # hit 在裁剪后坐标系
            hover_dwell_s=0.1,
            hold_s=0.1,
        )
        sleep(0.5)
        game_input.send_left_click_physical(
            ctx.hwnd,
            cx,
            cy,
            from_precrop=False,  # hit 在裁剪后坐标系
            hover_dwell_s=0.1,
            hold_s=0.1,
        )
        setattr(ctx.executor, "_manager_level_scroll_idx", 0)

        game_input.send_left_click_physical(ctx.hwnd, 1149, 712, hover_dwell_s=0.1, hold_s=0.1)
        return

    # 未匹配：滑动循环（上 2 次、下 2 次）
    if not ctx.cooldown.try_fire("manager:level:scroll", 2.0, ctx.monotonic):
        return
    idx = getattr(ctx.executor, "_manager_level_scroll_idx", 0)
    try:
        idx_i = int(idx)
    except Exception:
        idx_i = 0
    idx_i = idx_i % 8
    up = idx_i < 4

    x0, y0 = 99, 418
    dy = -150 if up else 150
    game_input.send_drag_physical(ctx.hwnd, x0, y0, x0, y0 + dy, hold_after_up_s=1)
    setattr(ctx.executor, "_manager_level_scroll_idx", (idx_i + 1) % 4)


def execute_finish_page(ctx: ManagerTickContext) -> None:
    """结束页面：点击领取。"""
    if not ctx.cooldown.try_fire("manager:finish-page-click", 1, ctx.monotonic):
        return
    game_input.send_left_click_physical(ctx.hwnd, 773, 605, hover_dwell_s=0.1, hold_s=0.1)


def execute_interact_page(ctx: ManagerTickContext) -> None:
    """店长特供交互页面：点击交互。"""
    if not ctx.cooldown.try_fire("manager:interact-page-click", 1, ctx.monotonic):
        return
    game_input.send_key_tap(ctx.hwnd, game_input.VK_F)


PAGE_HANDLERS: dict[str, Callable[[ManagerTickContext], None]] = {
    "skip-guide": execute_skip_guide,
    "manager-level": execute_manager_level,
    "finish-page": execute_finish_page,
    "interact-page": execute_interact_page,
}


def register_manager_pages(handlers: dict[str, Callable[[ManagerTickContext], None]]) -> None:
    handlers.update(PAGE_HANDLERS)
