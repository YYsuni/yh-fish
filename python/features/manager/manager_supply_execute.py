# -*- coding: utf-8 -*-
"""店长特供：根据 tick 快照执行日志与物理点击。"""

from __future__ import annotations

import tools.exec_msg as exec_msg
import tools.game_input as game_input

from features.manager.manager_tick import (
    CooldownGate,
    ManagerSupplyTickSnapshot,
)


def _format_foods_zh(foods: list[tuple[str, str, int]]) -> str:
    """将 foods 列表格式化为简短中文说明。"""
    if not foods:
        return "无订单项"
    parts: list[str] = []
    for name, itype, n in foods:
        if n > 0:
            parts.append(f"{name}×{n}")
    return "，".join(parts) if parts else "无有效数量"


def _format_kitchen_zh(kitchen: dict[str, str | int]) -> str:
    """将厨房字典格式化为简短中文说明。"""
    if not kitchen:
        return ""
    return "；" + "，".join(f"{key}: {val}" for key, val in kitchen.items())


def _star_count(kitchen: dict[str, str | int]) -> int:
    """读取 ``星星`` 槽位：整数个数，缺省或非数字视为 0。"""
    v = kitchen.get("星星")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and not isinstance(v, bool):
        return int(v)
    return 0


def _peak_by_types(
    foods: list[tuple[str, str, int]],
) -> tuple[str | None, int, str | None, int, str | None, int]:
    """饮料 / 主食 / 甜品各自当前峰值数量与对应名称（并列取 ``foods`` 中先出现者）。"""
    top_drink = top_staple = top_dessert = top_red_ribbon = None
    nd = ns = nde = nr = 0
    for name, itype, n in foods:
        if itype == "饮料" and n > nd:
            top_drink, nd = name, n
        elif itype == "主食" and n > ns:
            top_staple, ns = name, n
        elif itype == "甜品" and n > nde:
            top_dessert, nde = name, n
        elif itype == "红领巾" and n > nr:
            top_red_ribbon, nr = name, n
    return top_drink, nd, top_staple, ns, top_dessert, nde, top_red_ribbon, nr


def execute_manager_supply_tick(
    snapshot: ManagerSupplyTickSnapshot,
    cooldown: CooldownGate,
    *,
    direct_knock: bool = False,
) -> None:
    """根据快照节流输出日志，并按厨房/订单状态触发固定坐标点击。"""
    kitchen = snapshot.kitchen
    foods = snapshot.foods

    def click_physical(x: int, y: int, min_interval_s=0.3) -> None:
        """同一坐标节流后发送左键。"""
        if cooldown.try_fire(f"click:{x},{y}", min_interval_s, snapshot.monotonic):
            game_input.send_left_click_physical(snapshot.hwnd, x, y, hover_dwell_s=0.1, hold_s=0.1)

    if _star_count(kitchen) > 0:
        click_physical(30, 72, 0.8)
        return

    if direct_knock:
        click_physical(69, 347, 0.8)

    top_drink, drink_num, top_staple, staple_num, top_dessert, dessert_num, top_red_ribbon, red_ribbon_num = _peak_by_types(foods)

    if cooldown.try_fire("manager-log", 1.0, snapshot.monotonic):
        exec_msg.msg_out(
            "店长特供页面："
            f"{_format_foods_zh(foods)}"
            # f"{_format_kitchen_zh(kitchen)}"
        )

    # 备菜
    if kitchen.get("咖啡后台") == "空" and kitchen.get("咖啡机") == "空" and cooldown.try_fire("manager:coffee-back-empty-click", 0.5, snapshot.monotonic):
        click_physical(1030, 702)

    chop_empty = kitchen.get("切菜板") == "空"
    if chop_empty and kitchen.get("菜盘左") == "空":
        click_physical(85, 698)
    if chop_empty and kitchen.get("菜盘右") == "空":
        click_physical(481, 701)

    if kitchen.get("烤箱") == "空":
        click_physical(660, 702)

    if kitchen.get("甜品盘") == "空" and kitchen.get("烤箱") != "空":
        click_physical(857, 730)

    # 饮料制作
    cup = kitchen.get("饮料盘", "")
    if cup == "空" and drink_num > 0:
        if top_drink == "烤椰拿铁":
            click_physical(828, 556)
        elif top_drink == "冰摩卡":
            click_physical(1206, 567)

    elif cup in ("玻璃杯", "咖啡杯"):
        click_physical(1180, 702)
    elif cup == "咖啡":
        click_physical(909, 460)
    elif cup == "玻璃水":
        click_physical(1023, 459)

    # 甜品制作
    if kitchen.get("甜品盘") == "空" and kitchen.get("烤箱") != "空":
        click_physical(857, 730)
    if kitchen.get("甜品盘") != "空" and dessert_num > 0:
        click_physical(705, 480)

    # 主食制作
    if kitchen.get("主食盘") == "空":
        if staple_num > 0:
            if top_staple == "西红柿煎蛋可颂":
                click_physical(431, 568)
            elif top_staple == "金枪鱼三明治":
                click_physical(85, 574)
    elif kitchen.get("主食盘") == "面包片":
        click_physical(153, 471)
    elif kitchen.get("主食盘") == "牛角包":
        click_physical(265, 471)

    # 打红领巾
    if red_ribbon_num > 0:
        click_physical(69, 347)

    # 结束关卡
    if _star_count(kitchen) > 0:
        click_physical(30, 72, 0.8)
