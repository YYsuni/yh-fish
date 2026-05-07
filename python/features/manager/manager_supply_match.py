# -*- coding: utf-8 -*-
"""店长特供页 ``manager-supply``：按 ``food.json`` / ``kitchen.json`` 做图标与厨房槽位识别；满意度星星写在本模块常量中。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from features.page_match_paths import MANAGER_PAGES_JSON
from features.manager.manager_tick import ManagerSupplyTickSnapshot
from tools.page_template_match import (
    _match_template_in_precrop_roi_raw,
    match_template_multi_in_precrop_roi,
)

_log = logging.getLogger(__name__)

SUPPLY_MULTIMATCH_MIN_INTERVAL_S = 0.12
MANAGER_SUPPLY_PAGE_ID = "manager-supply"

_IMG = MANAGER_PAGES_JSON.parent
_FOOD_JSON = _IMG / "food.json"
_KITCHEN_JSON = _IMG / "kitchen.json"

# 饮品订单图标区（整窗未裁 [x,y,w,h]）
_ICON_REGION = (166.0, 121.0, 769.0, 208.0)

# 满意度星星：与订单区同为 ROI 内多数计数；不配 kitchen.json
_STAR_KITCHEN_KEY = "星星"
_STAR_REGION_PRECROP = (1203.0, 150.0, 37.0, 120.0)
_STAR_TEMPLATE_FILE = "五角星.png"

_FALLBACK_NAME = "店长特供"


def _load_json_doc(path: Path) -> Any:
    """读取 JSON 文件，失败时返回 None 并打日志。"""
    if not path.is_file():
        _log.warning("missing json: %s", path)
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _log.exception("parse json failed: %s", path)
        return None


def _parse_food_catalog() -> tuple[tuple[dict[str, Any], ...], frozenset[str]]:
    """解析 ``food.json``：返回 (行元组, 饮料名集合)。"""
    raw = _load_json_doc(_FOOD_JSON)
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return (), frozenset()
    for el in raw:
        if not isinstance(el, dict):
            continue
        name = el.get("name")
        itype = el.get("item_type")
        images = el.get("images")
        if not isinstance(name, str) or not isinstance(itype, str):
            continue
        if not isinstance(images, list):
            continue
        imgs = [str(x) for x in images if isinstance(x, str)]
        if not imgs:
            continue
        rows.append({"name": name.strip(), "item_type": itype.strip(), "images": imgs})
    drinks = frozenset(r["name"] for r in rows if r["item_type"] == "饮料")
    return tuple(rows), drinks


def _parse_kitchen_catalog() -> tuple[dict[str, Any], ...]:
    """解析 ``kitchen.json`` 为内部槽位定义（page 式单 ROI 状态）。"""
    raw = _load_json_doc(_KITCHEN_JSON)
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return ()
    for el in raw:
        if not isinstance(el, dict):
            continue
        name = el.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        region = el.get("region")
        if not isinstance(region, list) or len(region) != 4:
            continue
        try:
            rx, ry, rw, rh = (float(region[0]), float(region[1]), float(region[2]), float(region[3]))
        except (TypeError, ValueError):
            continue
        statuses: list[tuple[str, str]] = []
        st_raw = el.get("status")
        if isinstance(st_raw, list):
            for st in st_raw:
                if not isinstance(st, dict):
                    continue
                sn = st.get("status_name")
                tf = st.get("template_file")
                if isinstance(sn, str) and isinstance(tf, str):
                    statuses.append((sn.strip(), tf.strip()))
        out.append(
            {
                "name": name.strip(),
                "region": (rx, ry, rw, rh),
                "statuses": statuses,
            }
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class _Catalog:
    """惰性缓存的配置：食物行、图标模板、厨房槽位。"""

    food_rows: tuple[dict[str, Any], ...]
    icon_templates: tuple[tuple[str, str, str], ...]
    kitchen_slots: tuple[dict[str, Any], ...]


@lru_cache(maxsize=1)
def _catalog() -> _Catalog:
    """构建并缓存 ``food.json`` / ``kitchen.json`` 衍生结构。"""
    food_rows, drinks = _parse_food_catalog()
    tpls: list[tuple[str, str, str]] = []
    for r in food_rows:
        for fn in r["images"]:
            tpls.append((fn, r["name"], r["item_type"]))
    return _Catalog(
        food_rows=food_rows,
        icon_templates=tuple(tpls),
        kitchen_slots=_parse_kitchen_catalog(),
    )


def _iou_xywh(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """计算两矩形 IoU。"""
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


def _nms_hits(
    hits: list[dict[str, object]],
    *,
    iou_thresh: float,
    max_keep: int,
) -> list[dict[str, object]]:
    """按 similarity 做 NMS，抑制重叠框。"""

    def _box(d: dict[str, object]) -> tuple[int, int, int, int] | None:
        try:
            return (int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"]))
        except (KeyError, TypeError, ValueError):
            return None

    def _sim(d: dict[str, object]) -> float:
        v = d.get("similarity")
        return float(v) if isinstance(v, (int, float)) else 0.0

    if not hits or max_keep <= 0:
        return []
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


def _count_icons_by_name(items: list[dict[str, object]]) -> dict[str, int]:
    """图标命中 -> 展示名数量（排除占位名）。"""
    raw: dict[str, int] = {}
    for it in items:
        n = str(it.get("name") or "").strip()
        if not n or n == _FALLBACK_NAME:
            continue
        raw[n] = raw.get(n, 0) + 1
    return raw


def _foods_rows_from_counts(counts_by_name: dict[str, int]) -> list[tuple[str, str, int]]:
    """按 ``food.json`` 顺序输出 (中文名, 类型, 数量)；未在表中的匹配名附在末尾。"""
    cat = _catalog()
    out: list[tuple[str, str, int]] = []
    for r in cat.food_rows:
        name = r["name"]
        out.append((name, r["item_type"], int(counts_by_name.get(name, 0))))
    catalog_names = {r["name"] for r in cat.food_rows}
    for k, v in counts_by_name.items():
        if k not in catalog_names:
            out.append((k, "?", int(v)))
    return out


def _binary_slot_fallback(positive_label: str, *, slot_name: str) -> str:
    """单模板未达阈值：多数槽位 ``空``→``有``；``咖啡机`` 表示空闲的模板未命中则为 ``""``；其余为 ``""``。"""
    if positive_label == "空":
        if slot_name == "咖啡机":
            return ""
        return "有"
    return ""


def _count_star_instances(cropped_rgb: Image.Image, *, threshold: float) -> int:
    """满意度星星个数：与 ``_run_icon_multimatch`` 单饮品模板相同参数（ROI 内多数实例 + NMS）。"""
    p = _IMG / _STAR_TEMPLATE_FILE
    if not p.is_file():
        return 0
    raw = match_template_multi_in_precrop_roi(
        cropped_rgb,
        p,
        _STAR_REGION_PRECROP,
        threshold=float(threshold),
        max_matches=12,
        nms_iou=0.35,
    )
    hits = _nms_hits([dict(h) for h in raw if isinstance(h, dict)], iou_thresh=0.35, max_keep=20)
    return len(hits)


def _best_kitchen_status_page_style(
    cropped_rgb: Image.Image,
    region: tuple[float, float, float, float],
    statuses: list[tuple[str, str]],
    *,
    threshold: float,
) -> tuple[str, float] | None:
    """与 ``page_template_match._eval_page_features`` 一致：仅采纳 similarity≥阈值的模板，再取置信度最高的一条。"""
    best: tuple[str, float] | None = None
    th = float(threshold)
    for label, fn in statuses:
        p = _IMG / fn
        if not p.is_file():
            continue
        raw = _match_template_in_precrop_roi_raw(cropped_rgb, p, region)
        if raw is None:
            continue
        conf = float(raw[4])
        if conf < th:
            continue
        if best is None or conf > best[1]:
            best = (label, conf)
    return best


def _match_one_kitchen_slot(
    cropped_rgb: Image.Image,
    slot: dict[str, Any],
    *,
    threshold: float,
) -> str:
    """厨房槽位（json）：单 ROI 单结论，page 式多模板择优。"""
    region = slot["region"]
    statuses: list[tuple[str, str]] = slot["statuses"]
    slot_name = str(slot.get("name", ""))

    if not statuses:
        return ""

    picked = _best_kitchen_status_page_style(cropped_rgb, region, statuses, threshold=threshold)
    if picked is not None:
        return picked[0]

    if len(statuses) == 1:
        return _binary_slot_fallback(statuses[0][0], slot_name=slot_name)
    return "未知"


def _scan_kitchen_map(cropped_rgb: Image.Image, *, threshold: float) -> dict[str, str]:
    """遍历 ``kitchen.json`` 槽位，得到 {槽位名: 状态字符串}。"""
    out: dict[str, str] = {}
    for slot in _catalog().kitchen_slots:
        key = str(slot["name"])
        out[key] = _match_one_kitchen_slot(cropped_rgb, slot, threshold=threshold)
    return out


def _run_icon_multimatch(cropped_rgb: Image.Image, *, threshold: float) -> dict[str, Any]:
    """订单区多模板多实例匹配，返回 items 与 counts。"""
    t0 = time.perf_counter()
    parts: list[dict[str, object]] = []
    ok = False
    for fn, disp, itype in _catalog().icon_templates:
        p = _IMG / fn
        if not p.is_file():
            continue
        ok = True
        raw = match_template_multi_in_precrop_roi(
            cropped_rgb,
            p,
            _ICON_REGION,
            threshold=float(threshold),
            max_matches=12,
            nms_iou=0.35,
        )
        for it in raw:
            row = dict(it)
            row["name"] = disp
            row["type"] = itype
            row["template_file"] = fn
            parts.append(row)
    ms = (time.perf_counter() - t0) * 1000.0
    if not ok:
        return {
            "match_ms": round(ms, 3),
            "items": [],
            "counts": {},
            "error": "template_missing",
        }
    items = _nms_hits(parts, iou_thresh=0.35, max_keep=20)
    counts = _count_icons_by_name(items)
    return {"match_ms": round(ms, 3), "items": items, "counts": counts}


def gather_manager_supply_tick(
    executor: Any,
    *,
    monotonic: float,
    hwnd: int,
    page_match: dict[str, object],
) -> ManagerSupplyTickSnapshot:
    """从执行器读取本帧识别结果，组装 tick 快照。"""
    _ = page_match
    hits = executor.supply_match_items_snapshot()
    cnt = _count_icons_by_name([dict(h) for h in hits if isinstance(h, dict)])
    foods = _foods_rows_from_counts(cnt)

    md = executor.supply_match_debug_snapshot()
    kitchen: dict[str, str | int] = {}
    if isinstance(md, dict):
        raw_k = md.get("kitchen")
        if isinstance(raw_k, dict):
            for a, b in raw_k.items():
                kk = str(a)
                if isinstance(b, int):
                    kitchen[kk] = b
                elif isinstance(b, float) and not isinstance(b, bool) and float(b).is_integer():
                    kitchen[kk] = int(b)
                else:
                    kitchen[kk] = str(b)

    return ManagerSupplyTickSnapshot(monotonic=monotonic, hwnd=hwnd, foods=foods, kitchen=kitchen)


def maybe_run_supply_multimatch(executor: Any, now: float, page_id: str | None) -> None:
    """店长「特供」页：节流跑一次图标多模板匹配与厨房槽位扫描，结果写入 ``executor._match_debug``。"""

    # 离开特供页：清空匹配调试，防止残留
    if page_id != MANAGER_SUPPLY_PAGE_ID:
        with executor._lock:
            executor._clear_match_debug_unlocked()
        return
    # 未到间隔则跳过，降低 CPU
    if not executor._cooldown.try_fire("manager:supply:multimatch", SUPPLY_MULTIMATCH_MIN_INTERVAL_S, now):
        return
    cropped = executor._capture.get_last_cropped_rgb_copy()
    if cropped is None:
        with executor._lock:
            executor._clear_match_debug_unlocked()
        return
    th = float(executor._capture.get_status().page_match_threshold)
    # 特供页图标：多模板匹配 + NMS，得到 items / counts
    try:
        icon_dbg = _run_icon_multimatch(cropped, threshold=th)
    except Exception:
        _log.exception("icon multimatch failed")
        icon_dbg = {"match_ms": 0.0, "items": [], "counts": {}, "error": "match_failed"}

    # 厨房：page 式单 ROI 单标签（kitchen.json）
    try:
        kitchen_map: dict[str, str | int] = dict(_scan_kitchen_map(cropped, threshold=th))
    except Exception:
        _log.exception("kitchen scan failed")
        kitchen_map = {}

    # 满意度星星：多数计数，单独于厨房槽位
    try:
        kitchen_map[_STAR_KITCHEN_KEY] = _count_star_instances(cropped, threshold=th)
    except Exception:
        _log.exception("star match failed")

    counts = icon_dbg.get("counts") if isinstance(icon_dbg.get("counts"), dict) else {}
    cnt_map: dict[str, int] = {}
    if isinstance(counts, dict):
        for k, v in counts.items():
            try:
                cnt_map[str(k)] = int(v)
            except (TypeError, ValueError):
                pass

    dbg: dict[str, Any] = dict(icon_dbg) if isinstance(icon_dbg, dict) else {}
    dbg["kitchen"] = kitchen_map
    dbg["foods"] = _foods_rows_from_counts(cnt_map)

    with executor._lock:
        executor._match_debug = dbg
