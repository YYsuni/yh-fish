# -*- coding: utf-8 -*-
"""店长特供页 ``manager-supply``：模板匹配、槽位跟踪、上菜与咖啡后台点击。"""

from __future__ import annotations

import logging
import time
from typing import Any

from PIL import Image

from features.auto_fish_page_match import MANAGER_PAGES_JSON
from features.manager_supply_execute import execute_manager_supply_tick
from features.manager_supply_snapshot import (
    ManagerSupplyDrinkPick,
    ManagerSupplySlotTrack,
    ManagerSupplyTickSnapshot,
)
from features.manager_tick import CooldownGate, ManagerTickContext
from tools.page_template_match import (
    _match_template_in_precrop_roi_raw,
    match_template_multi_in_precrop_roi,
    match_template_score_in_precrop_roi,
)

import tools.exec_msg as exec_msg

_log = logging.getLogger(__name__)

# 多实例模板匹配仅在本线程内节流执行，避免占用捕获管线帧循环。
SUPPLY_MULTIMATCH_MIN_INTERVAL_S = 0.12

# --- 店长特供页内饮品图标多实例识别（整窗未裁坐标 region；与 page.json 无关，后续可整理配置）---
_MANAGER_SUPPLY_ICON_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("烤椰拿铁1.png", "烤椰拿铁"),
    ("烤椰拿铁2.png", "烤椰拿铁"),
    ("冰摩卡1.png", "冰摩卡"),
    ("冰摩卡2.png", "冰摩卡"),
)
_MANAGER_SUPPLY_ICON_REGION_PRECROP = (166.0, 121.0, 769.0, 208.0)
_MANAGER_IMG_DIR = MANAGER_PAGES_JSON.parent
_ITEM_NAME_FALLBACK = "店长特供"

_COFFEE_BACK_EMPTY_FILE = "咖啡后台-空.png"
_COFFEE_BACK_EMPTY_REGION_PRECROP = (1119.92, 659.71, 141.9, 101.2)

_CUP_PLATE_REGION_PRECROP = (954.87, 545.13, 113.25, 77.81)
_CUP_PLATE_SLOT_TOL_PX = 5
_DRINK_SUPPLY_SLOT_TOL_PX = 5
_DRINK_AUTOMATION_NAMES: frozenset[str] = frozenset({"烤椰拿铁", "冰摩卡"})

_CUP_PLATE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("杯子盘-空.png", "空"),
    ("杯子盘-玻璃杯.png", "玻璃杯"),
    ("杯子盘-玻璃水.png", "玻璃水"),
    ("杯子盘-咖啡杯.png", "咖啡杯"),
    ("杯子盘-咖啡.png", "咖啡"),
)


def _supply_display_name_order() -> list[str]:
    seen: list[str] = []
    for _fn, disp in _MANAGER_SUPPLY_ICON_TEMPLATES:
        if disp not in seen:
            seen.append(disp)
    return seen


def _supply_counts_payload(items: list[dict[str, object]]) -> dict[str, int]:
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


def _format_supply_counts_zh(counts: dict[str, int]) -> str:
    if not counts:
        return "无有效分类"
    return "，".join(f"{k} {v} 个" for k, v in counts.items())


def _iou_xywh(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
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
    t0 = time.perf_counter()
    parts: list[dict[str, object]] = []
    found = False
    for fn, disp_name in _MANAGER_SUPPLY_ICON_TEMPLATES:
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
        out["cup_plate_peak"] = None
    elif best_s >= float(threshold):
        out["cup_plate"] = best_label
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
        out["cup_plate_peak"] = None
    return out


def _slots_update_from_hits(
    prev: list[ManagerSupplySlotTrack],
    hits: list[tuple[int, int, str]],
    *,
    now: float,
    tol_px: int,
) -> list[ManagerSupplySlotTrack]:
    remaining = list(prev)
    out: list[ManagerSupplySlotTrack] = []
    for cx, cy, lab in hits:
        best_j: int | None = None
        for j, s in enumerate(remaining):
            if max(abs(s.cx - cx), abs(s.cy - cy)) <= tol_px:
                best_j = j
                break
        if best_j is not None:
            s = remaining.pop(best_j)
            first = s.first_seen if s.label == lab else now
            out.append(ManagerSupplySlotTrack(cx, cy, lab, first, now))
        else:
            out.append(ManagerSupplySlotTrack(cx, cy, lab, now, now))
    return out


def _slots_sorted_payload(slots: list[ManagerSupplySlotTrack]) -> list[dict[str, object]]:
    rows = [
        {
            "cx": t.cx,
            "cy": t.cy,
            "label": t.label,
            "first_seen_mono": round(t.first_seen, 4),
            "last_seen_mono": round(t.last_seen, 4),
        }
        for t in slots
    ]
    rows.sort(key=lambda r: float(r["first_seen_mono"]))
    return rows


def _drink_hits_from_items(items: list[object]) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for el in items:
        if not isinstance(el, dict):
            continue
        name = str(el.get("name") or "").strip()
        if name not in _DRINK_AUTOMATION_NAMES:
            continue
        try:
            x, y, w, h = int(el["x"]), int(el["y"]), int(el["w"]), int(el["h"])
        except (KeyError, TypeError, ValueError):
            continue
        hits.append((x + w // 2, y + h // 2, name))
    return hits


def _cup_hits_from_match_debug(dbg: dict[str, object]) -> list[tuple[int, int, str]]:
    cp = dbg.get("cup_plate")
    peak = dbg.get("cup_plate_peak")
    if not isinstance(cp, str) or cp == "未知":
        return []
    if not isinstance(peak, dict):
        return []
    try:
        cx = int(peak["cx"])
        cy = int(peak["cy"])
    except (KeyError, TypeError, ValueError):
        return []
    return [(cx, cy, cp)]


def gather_manager_supply_tick(
    executor: Any,
    *,
    monotonic: float,
    hwnd: int,
    page_match: dict[str, object],
) -> ManagerSupplyTickSnapshot:
    """从执行器读取本帧店长特供相关数据（不发送输入）。"""
    _ = page_match
    hits = executor.supply_match_items_snapshot()
    counts = _supply_counts_payload([dict(h) for h in hits if isinstance(h, dict)])
    md = executor.supply_match_debug_snapshot()
    mdd = md if isinstance(md, dict) else {}
    cb = mdd.get("coffee_back_bar")
    cbs = mdd.get("coffee_back_bar_similarity")
    cp = mdd.get("cup_plate")
    cb_s = f"{float(cbs):.3f}" if isinstance(cbs, (int, float)) else "—"
    cb_v = str(cb) if cb is not None else "—"
    cp_v = str(cp) if cp is not None else "—"
    latch = executor.serve_cup_latch_get()
    slot = executor.peek_earliest_automation_drink()
    pick: ManagerSupplyDrinkPick | None = None
    if slot is not None:
        pick = ManagerSupplyDrinkPick(label=slot.label, cx=slot.cx, cy=slot.cy)
    return ManagerSupplyTickSnapshot(
        monotonic=monotonic,
        hwnd=hwnd,
        cb_v=cb_v,
        cp_v=cp_v,
        cb_s=cb_s,
        counts=counts,
        serve_cup_latch=latch,
        earliest_drink=pick,
    )


def page_manager_supply(ctx: ManagerTickContext) -> None:
    """兼容入口：采集 + 执行（轮询内也可分两步直接调 gather / execute）。"""
    snap = gather_manager_supply_tick(
        ctx.executor,
        monotonic=ctx.monotonic,
        hwnd=ctx.hwnd,
        page_match=ctx.page_match,
    )
    execute_manager_supply_tick(snap, ctx.executor, ctx.cooldown)


def maybe_run_supply_multimatch(executor: Any, now: float, page_id: str | None) -> None:
    """仅在执行器已启动且当前为店长特供页时，对最新裁剪帧做多实例匹配（节流）。"""
    if page_id != "manager-supply":
        with executor._lock:
            executor._clear_match_debug_unlocked()
            executor._cup_plate_tracks.clear()
            executor._drink_tracks.clear()
        return
    if not executor._cooldown.try_fire("manager:supply:multimatch", SUPPLY_MULTIMATCH_MIN_INTERVAL_S, now):
        return
    cropped = executor._capture.get_last_cropped_rgb_copy()
    if cropped is None:
        with executor._lock:
            executor._clear_match_debug_unlocked()
            executor._cup_plate_tracks.clear()
            executor._drink_tracks.clear()
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
        if isinstance(dbg, dict):
            cup_hits = _cup_hits_from_match_debug(dbg)
            raw_items = dbg.get("items")
            items_list = raw_items if isinstance(raw_items, list) else []
            drink_hits = _drink_hits_from_items(items_list)
            executor._cup_plate_tracks = _slots_update_from_hits(
                executor._cup_plate_tracks,
                cup_hits,
                now=now,
                tol_px=_CUP_PLATE_SLOT_TOL_PX,
            )
            executor._drink_tracks = _slots_update_from_hits(
                executor._drink_tracks,
                drink_hits,
                now=now,
                tol_px=_DRINK_SUPPLY_SLOT_TOL_PX,
            )
            dbg["cup_plate_slots"] = _slots_sorted_payload(executor._cup_plate_tracks)
            dbg["drink_supply_slots"] = _slots_sorted_payload(executor._drink_tracks)
        executor._match_debug = dbg


MANAGER_SUPPLY_PAGE_ID = "manager-supply"

# 历史命名兼容（grep / 文档）
_page_manager_supply = page_manager_supply

# 供 ``manager_executor`` 等模块引用，避免跨模块访问私有名
DRINK_AUTOMATION_NAMES = _DRINK_AUTOMATION_NAMES
DRINK_SUPPLY_SLOT_TOL_PX = _DRINK_SUPPLY_SLOT_TOL_PX
