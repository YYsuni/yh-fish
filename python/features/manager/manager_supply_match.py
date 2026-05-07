# -*- coding: utf-8 -*-
"""店长特供页 ``manager-supply``：模板匹配、槽位跟踪、上菜与咖啡后台点击。"""

from __future__ import annotations

import logging
import time
from typing import Any

from PIL import Image

from features.page_match_paths import MANAGER_PAGES_JSON
from features.manager.manager_tick import ManagerSupplyTickSnapshot
from tools.page_template_match import (
    _match_template_in_precrop_roi_raw,
    match_template_multi_in_precrop_roi,
    match_template_score_in_precrop_roi,
)

import tools.exec_msg as exec_msg

_log = logging.getLogger(__name__)

# 多实例模板匹配仅在本线程内节流执行，避免占用捕获管线帧循环。
SUPPLY_MULTIMATCH_MIN_INTERVAL_S = 0.12

# --- 店长特供页内物品图标多实例识别（整窗未裁坐标 region；与 page.json 无关，后续可整理配置）---
# tuple: (template_file, display_name, item_type)
_MANAGER_SUPPLY_ICON_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    # 饮料
    ("烤椰拿铁1.png", "烤椰拿铁", "饮料"),
    ("烤椰拿铁2.png", "烤椰拿铁", "饮料"),
    ("冰摩卡1.png", "冰摩卡", "饮料"),
    ("冰摩卡2.png", "冰摩卡", "饮料"),
    # 甜品
    ("苹果派1.png", "苹果派", "甜品"),
    ("苹果派2.png", "苹果派", "甜品"),
    # 主食
    ("西红柿煎蛋可颂1.png", "西红柿煎蛋可颂", "主食"),
    ("西红柿煎蛋可颂2.png", "西红柿煎蛋可颂", "主食"),
    ("金枪鱼三明治1.png", "金枪鱼三明治", "主食"),
    ("金枪鱼三明治2.png", "金枪鱼三明治", "主食"),
)
_MANAGER_SUPPLY_ICON_REGION_PRECROP = (166.0, 121.0, 769.0, 208.0)
_MANAGER_IMG_DIR = MANAGER_PAGES_JSON.parent
_ITEM_NAME_FALLBACK = "店长特供"

# --- 供后续「空闲状态」匹配用（每个状态对应不同 region；位置你后续手写；先占位）---
# tuple: (template_file, status_name, region_precrop_xywh)
_MANAGER_SUPPLY_STATUS_TEMPLATES: tuple[tuple[str, str, tuple[float, float, float, float]], ...] = (
    ("烤箱-空.png", "烤箱-空", (0.0, 0.0, 0.0, 0.0)),
    ("菜盘右-空.png", "菜盘右-空", (0.0, 0.0, 0.0, 0.0)),
    ("菜盘左-空.png", "菜盘左-空", (0.0, 0.0, 0.0, 0.0)),
    ("切菜板-空.png", "切菜板-空", (0.0, 0.0, 0.0, 0.0)),
    ("中盘-空.png", "中盘-空", (0.0, 0.0, 0.0, 0.0)),
)

_COFFEE_BACK_EMPTY_FILE = "咖啡后台-空.png"
_COFFEE_BACK_EMPTY_REGION_PRECROP = (1119.92, 659.71, 141.9, 101.2)

_COFFEE_MACHINE_IDLE_FILE = "咖啡机-空闲.png"
# 咖啡机状态区域（整窗未裁坐标系 [x,y,w,h]）
_COFFEE_MACHINE_IDLE_REGION_PRECROP = (1023.0, 676.0, 79.0, 80.0)

_CUP_PLATE_REGION_PRECROP = (954.87, 545.13, 113.25, 77.81)
_DRINK_AUTOMATION_NAMES: frozenset[str] = frozenset({"烤椰拿铁", "冰摩卡"})

_SCORE_STAR_FILE = "五角星.png"
# 分数区域（整窗未裁坐标系 [x,y,w,h]）
_SCORE_STAR_REGION_PRECROP = (1203.0, 150.0, 37.0, 120.0)

_CUP_PLATE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("杯子盘-空.png", "空"),
    ("杯子盘-玻璃杯.png", "玻璃杯"),
    ("杯子盘-玻璃水.png", "玻璃水"),
    ("杯子盘-咖啡杯.png", "咖啡杯"),
    ("杯子盘-咖啡.png", "咖啡"),
)


def _supply_display_name_order() -> list[str]:
    """按模板配置的顺序生成展示用饮品名列表（去重保序）。"""
    seen: list[str] = []
    for _fn, disp, _tp in _MANAGER_SUPPLY_ICON_TEMPLATES:
        if disp not in seen:
            seen.append(disp)
    return seen


def _supply_counts_payload(items: list[dict[str, object]]) -> dict[str, int]:
    """把多实例匹配结果聚合成「饮品名 -> 数量」的统计字典，并按展示顺序输出。"""
    raw: dict[str, int] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        n = str(it.get("name") or "").strip()
        if not n or n == _ITEM_NAME_FALLBACK:
            continue
        raw[n] = raw.get(n, 0) + 1
    ordered: dict[str, int] = {}
    for disp in _supply_display_name_order():
        ordered[disp] = int(raw.get(disp, 0))
    for k, v in raw.items():
        if k not in ordered:
            ordered[k] = int(v)
    return ordered


def _iou_xywh(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """计算两个矩形框（xywh）之间的 IoU（交并比）。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    a_x2, a_y2 = ax + aw, ay + ah
    b_x2, b_y2 = bx + bw, by + bh
    ix0, iy0 = max(ax, bx), max(ay, by)
    ix1, iy1 = min(a_x2, b_x2), min(a_y2, b_y2)
    iw_, ih_ = ix1 - ix0, iy1 - iy0
    if iw_ <= 0 or ih_ <= 0:
        return 0.0
    inter = float(iw_ * ih_)
    ua = float(aw * ah + bw * bh) - inter
    return inter / ua if ua > 0 else 0.0


def _nms_supply_hit_dicts(
    hits: list[dict[str, object]],
    *,
    iou_thresh: float,
    max_keep: int,
) -> list[dict[str, object]]:
    """对匹配命中框做简单 NMS 去重（按 similarity 降序，IoU 超阈值则抑制）。"""
    if not hits or max_keep <= 0:
        return []

    def _box(d: dict[str, object]) -> tuple[int, int, int, int] | None:
        try:
            return (int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
        except (KeyError, TypeError, ValueError):
            return None

    def _sim(d: dict[str, object]) -> float:
        v = d.get("similarity")
        return float(v) if isinstance(v, (int, float)) else 0.0

    ordered = sorted(hits, key=_sim, reverse=True)
    kept: list[dict[str, object]] = []
    for h in ordered:
        if len(kept) >= max_keep:
            break
        bh = _box(h)
        if bh is None:
            continue
        if any(_iou_xywh(bh, kb) >= iou_thresh for kb in (_box(k) for k in kept) if kb is not None):
            continue
        kept.append(h)
    return kept


def _run_manager_supply_icon_multimatch(cropped_rgb: Image.Image, *, threshold: float) -> dict[str, object] | None:
    """对店长特供页的饮品图标区域做多模板多实例匹配，并返回调试信息与统计。"""
    t0 = time.perf_counter()
    parts: list[dict[str, object]] = []
    found = False
    for fn, disp_name, item_type in _MANAGER_SUPPLY_ICON_TEMPLATES:
        tpl = _MANAGER_IMG_DIR / fn
        if not tpl.is_file():
            continue
        found = True
        raw = match_template_multi_in_precrop_roi(
            cropped_rgb,
            tpl,
            _MANAGER_SUPPLY_ICON_REGION_PRECROP,
            threshold=float(threshold),
            max_matches=12,
            nms_iou=0.35,
        )
        for it in raw:
            row = dict(it)
            row["name"] = disp_name
            row["type"] = item_type
            row["template_file"] = fn
            parts.append(row)
    ms = (time.perf_counter() - t0) * 1000.0
    if not found:
        empty_items: list[dict[str, object]] = []
        return {
            "match_ms": round(ms, 3),
            "items": empty_items,
            "counts": _supply_counts_payload(empty_items),
            "error": "template_missing",
        }
    items = _nms_supply_hit_dicts(parts, iou_thresh=0.35, max_keep=20)
    return {
        "match_ms": round(ms, 3),
        "items": items,
        "counts": _supply_counts_payload(items),
    }


def _manager_aux_region_fields(cropped_rgb: Image.Image, *, threshold: float) -> dict[str, object]:
    """补充店长特供页的辅助区域识别字段（咖啡后台条、咖啡机状态、杯子盘状态、各工作台空闲状态）。"""
    out: dict[str, object] = {}
    cb_path = _MANAGER_IMG_DIR / _COFFEE_BACK_EMPTY_FILE
    cb_score = match_template_score_in_precrop_roi(cropped_rgb, cb_path, _COFFEE_BACK_EMPTY_REGION_PRECROP)
    if cb_score is not None:
        s = float(cb_score)
        out["coffee_back_bar_similarity"] = round(s, 4)
        out["coffee_back_bar"] = "空" if s >= float(threshold) else "有"
    else:
        out["coffee_back_bar_similarity"] = None
        out["coffee_back_bar"] = "有"

    cm_path = _MANAGER_IMG_DIR / _COFFEE_MACHINE_IDLE_FILE
    cm_score = match_template_score_in_precrop_roi(cropped_rgb, cm_path, _COFFEE_MACHINE_IDLE_REGION_PRECROP)
    if cm_score is not None:
        s = float(cm_score)
        out["coffee_machine_similarity"] = round(s, 4)
        out["coffee_machine_status"] = "空闲" if s >= float(threshold) else "使用中"
    else:
        out["coffee_machine_similarity"] = None
        out["coffee_machine_status"] = "使用中"

    sims: dict[str, float] = {}
    best_label = "未知"
    best_s = -1.0
    best_raw: tuple[int, int, int, int, float] | None = None
    for fn, label in _CUP_PLATE_TEMPLATES:
        p = _MANAGER_IMG_DIR / fn
        raw = _match_template_in_precrop_roi_raw(cropped_rgb, p, _CUP_PLATE_REGION_PRECROP)
        if raw is None:
            continue
        fv = float(raw[4])
        sims[label] = fv
        if fv > best_s:
            best_s = fv
            best_label = label
            best_raw = raw
    out["cup_plate_similarities"] = {k: round(v, 4) for k, v in sims.items()}
    if best_s < 0:
        out["cup_plate"] = "未知"
        out["cup_plate_similarity"] = None
        out["cup_plate_peak"] = None
    elif best_s >= float(threshold):
        out["cup_plate"] = best_label
        out["cup_plate_similarity"] = round(float(best_s), 4)
        if best_raw is not None:
            bx, by, bw, bh = best_raw[0], best_raw[1], best_raw[2], best_raw[3]
            out["cup_plate_peak"] = {
                "x": int(bx),
                "y": int(by),
                "w": int(bw),
                "h": int(bh),
                "cx": int(bx + bw // 2),
                "cy": int(by + bh // 2),
            }
        else:
            out["cup_plate_peak"] = None
    else:
        out["cup_plate"] = "未知"
        out["cup_plate_similarity"] = round(float(best_s), 4)
        out["cup_plate_peak"] = None

    # 各工作台「空闲状态」：每个模板对应不同 region
    status_similarities: dict[str, float | None] = {}
    status_values: dict[str, str] = {}
    for fn, status_name, region in _MANAGER_SUPPLY_STATUS_TEMPLATES:
        p = _MANAGER_IMG_DIR / fn
        if not p.is_file():
            status_similarities[status_name] = None
            status_values[status_name] = "未知"
            continue
        s0 = match_template_score_in_precrop_roi(cropped_rgb, p, region)
        if s0 is None:
            status_similarities[status_name] = None
            status_values[status_name] = "未知"
            continue
        s = float(s0)
        status_similarities[status_name] = round(s, 4)
        status_values[status_name] = "空" if s >= float(threshold) else "有"
    out["supply_status_similarities"] = status_similarities
    out["supply_status"] = status_values

    # 分数：五角星多实例匹配（允许多个）
    star_path = _MANAGER_IMG_DIR / _SCORE_STAR_FILE
    if star_path.is_file():
        try:
            star_hits = match_template_multi_in_precrop_roi(
                cropped_rgb,
                star_path,
                _SCORE_STAR_REGION_PRECROP,
                threshold=float(threshold),
                max_matches=12,
                nms_iou=0.2,
            )
            # 只做轻量 NMS，避免同一颗星在相邻像素重复命中
            out["score"] = _nms_supply_hit_dicts([dict(h) for h in star_hits if isinstance(h, dict)], iou_thresh=0.2, max_keep=20)
        except Exception:
            _log.exception("score star multi match failed")
            out["score"] = []
    else:
        out["score"] = []
    return out


def gather_manager_supply_tick(
    executor: Any,
    *,
    monotonic: float,
    hwnd: int,
    page_match: dict[str, object],
) -> ManagerSupplyTickSnapshot:
    """从执行器读取本帧店长特供相关数据。"""
    _ = page_match
    hits = executor.supply_match_items_snapshot()
    counts = _supply_counts_payload([dict(h) for h in hits if isinstance(h, dict)])
    md = executor.supply_match_debug_snapshot()
    mdd = md if isinstance(md, dict) else {}
    cb = mdd.get("coffee_back_bar")
    cbs = mdd.get("coffee_back_bar_similarity")
    cp = mdd.get("cup_plate")
    cps = mdd.get("cup_plate_similarity")
    cms = mdd.get("coffee_machine_status")
    cmss = mdd.get("coffee_machine_similarity")
    supply_status = mdd.get("supply_status")
    supply_status_similarities = mdd.get("supply_status_similarities")
    score_hits = mdd.get("score")
    score_items: list[dict[str, object]] = []
    if isinstance(score_hits, list):
        for el in score_hits:
            if isinstance(el, dict):
                score_items.append(dict(el))
    cb_s = f"{float(cbs):.3f}" if isinstance(cbs, (int, float)) else "—"
    cb_v = str(cb) if cb is not None else "—"
    cp_v = str(cp) if cp is not None else "—"
    coffee_machine_status = str(cms) if cms is not None else "—"
    supply_status_v: dict[str, str] = {}
    if isinstance(supply_status, dict):
        for k, v in supply_status.items():
            supply_status_v[str(k)] = str(v)
    supply_status_sims_v: dict[str, float | None] = {}
    if isinstance(supply_status_similarities, dict):
        for k, v in supply_status_similarities.items():
            kk = str(k)
            if v is None:
                supply_status_sims_v[kk] = None
            elif isinstance(v, (int, float)):
                supply_status_sims_v[kk] = float(v)
            else:
                supply_status_sims_v[kk] = None

    # 把旧状态也并入统一的 supply_status 结构，便于上层只处理一套字段
    supply_status_v.setdefault("咖啡后台条", cb_v)
    supply_status_v.setdefault("咖啡机", coffee_machine_status)
    supply_status_v.setdefault("杯子盘", cp_v)
    if isinstance(cbs, (int, float)):
        supply_status_sims_v.setdefault("咖啡后台条", float(cbs))
    if isinstance(cmss, (int, float)):
        supply_status_sims_v.setdefault("咖啡机", float(cmss))
    if isinstance(cps, (int, float)):
        supply_status_sims_v.setdefault("杯子盘", float(cps))
    return ManagerSupplyTickSnapshot(
        monotonic=monotonic,
        hwnd=hwnd,
        cb_v=cb_v,
        coffee_machine_status=coffee_machine_status,
        cp_v=cp_v,
        cb_s=cb_s,
        counts=counts,
        score=score_items,
        supply_status=supply_status_v,
        supply_status_similarities=supply_status_sims_v,
    )


def maybe_run_supply_multimatch(executor: Any, now: float, page_id: str | None) -> None:
    """仅在执行器已启动且当前为店长特供页时，对最新裁剪帧做多实例匹配（节流）。"""
    if page_id != "manager-supply":
        with executor._lock:
            executor._clear_match_debug_unlocked()
        return
    if not executor._cooldown.try_fire("manager:supply:multimatch", SUPPLY_MULTIMATCH_MIN_INTERVAL_S, now):
        return
    cropped = executor._capture.get_last_cropped_rgb_copy()
    if cropped is None:
        with executor._lock:
            executor._clear_match_debug_unlocked()
        return
    st = executor._capture.get_status()
    th = float(st.page_match_threshold)
    try:
        dbg = _run_manager_supply_icon_multimatch(cropped, threshold=th)
    except Exception:
        _log.exception("manager supply icon multi match failed")
        dbg = {
            "match_ms": 0.0,
            "items": [],
            "counts": _supply_counts_payload([]),
            "error": "match_failed",
        }
    if isinstance(dbg, dict):
        try:
            dbg.update(_manager_aux_region_fields(cropped, threshold=th))
        except Exception:
            _log.exception("manager aux region fields failed")
    with executor._lock:
        executor._match_debug = dbg


MANAGER_SUPPLY_PAGE_ID = "manager-supply"

# 供 ``manager_executor`` 等模块引用，避免跨模块访问私有名
DRINK_AUTOMATION_NAMES = _DRINK_AUTOMATION_NAMES
