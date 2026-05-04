# -*- coding: utf-8 -*-
"""根据 `images/auto_fish/pages.json` 与模板 PNG，对裁剪后的游戏画面做 OpenCV 模板匹配。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from tools.window_capture import WGC_SNAPSHOT_MARGIN_LR_PX

DEFAULT_PAGES_JSON = Path(__file__).resolve().parents[1] / "images" / "auto_fish" / "pages.json"
DEFAULT_MATCH_THRESHOLD = 0.5
# pages.json 的 region 基于“未裁剪前整窗截图”的坐标；捕获时会默认裁掉这些边缘。
DEFAULT_PRE_CROP_TOP_PX = 52
DEFAULT_PRE_CROP_LEFT_PX = WGC_SNAPSHOT_MARGIN_LR_PX


@dataclass(frozen=True)
class PageMatchResult:
    """匹配结果：标签为 pages.json 中 `label`；矩形为裁剪去边距后的客户区像素（与捕获 status 宽高同坐标系）。"""

    page_id: str
    label: str
    confidence: float  # TM_CCOEFF_NORMED 峰值按通道数归一化，便于与单色时代阈值相当，约 [0,1]
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class _FeatureTemplate:
    """`region_cropped` 为游戏画面裁剪坐标系下的搜索矩形；`tpl_rgb` 为整张模板 PNG（在 ROI 内匹配）。"""

    region_cropped: tuple[int, int, int, int]
    tpl_rgb: np.ndarray


def _apply_pre_crop_offset(
    rect: list[object] | tuple[object, object, object, object],
    *,
    left_px: int,
    top_px: int,
) -> list[float]:
    """将未裁剪坐标系的 rect=[x,y,w,h] 映射到裁剪后坐标系（仅平移 x/y）。"""
    x, y, w, h = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
    return [x - float(left_px), y - float(top_px), w, h]


def _crop_rgb_by_rect(
    rgb: np.ndarray,
    rect: list[int] | tuple[int, int, int, int],
) -> np.ndarray | None:
    """按 rect=[x,y,w,h] 裁剪 RGB(uint8, HxWx3)；允许越界（会 clamp），返回 None 表示裁剪无效。"""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        return None
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        return None
    try:
        x, y, w, h = (int(round(float(v))) for v in rect)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None

    ih, iw = int(rgb.shape[0]), int(rgb.shape[1])
    if ih <= 0 or iw <= 0:
        return None

    x0 = max(0, x)
    y0 = max(0, y)
    x1 = min(iw, x0 + w)
    y1 = min(ih, y0 + h)
    if x1 <= x0 or y1 <= y0:
        return None
    out = rgb[y0:y1, x0:x1]
    oh, ow = int(out.shape[0]), int(out.shape[1])
    if oh < 2 or ow < 2:
        return None
    return out


def _match_template_in_roi(
    scene_rgb: np.ndarray,
    region: tuple[int, int, int, int],
    tpl_rgb: np.ndarray,
) -> tuple[int, int, int, int, float] | None:
    """在 `scene_rgb` 的 region ROI 内对 `tpl_rgb` 做模板匹配；返回 (全局 x, 全局 y, w, h, score)。"""
    rx, ry, _, _ = region
    roi = _crop_rgb_by_rect(scene_rgb, region)
    if roi is None:
        return None
    sh, sw = roi.shape[:2]
    th, tw = tpl_rgb.shape[:2]
    if th > sh or tw > sw or th < 1 or tw < 1:
        return None
    res = cv2.matchTemplate(roi, tpl_rgb, cv2.TM_CCOEFF_NORMED)
    _min_v, max_v, _min_loc, max_loc = cv2.minMaxLoc(res)
    mx, my = max_loc
    return (rx + mx, ry + my, tw, th, float(max_v))


def match_template_in_precrop_roi(
    cropped_rgb: Image.Image,
    template_path: Path,
    region_xywh_precrop: tuple[float, float, float, float],
    *,
    threshold: float,
) -> tuple[int, int, int, int, float] | None:
    """在「整窗未裁」坐标系的矩形 ROI 内对单张模板做 TM_CCOEFF_NORMED；`cropped_rgb` 须与捕获管线裁剪后坐标系一致。

    与 `pages.json` 中 `region` 相同：先减 `DEFAULT_PRE_CROP_LEFT_PX` / `DEFAULT_PRE_CROP_TOP_PX`。
    成功返回 ``(x, y, w, h, confidence)``，否则 None。
    """
    if not template_path.is_file():
        return None
    try:
        im = Image.open(template_path).convert("RGB")
        tpl_rgb = np.asarray(im)
    except OSError:
        return None
    if tpl_rgb.ndim != 3 or tpl_rgb.shape[2] != 3:
        return None
    try:
        rect_adj = _apply_pre_crop_offset(
            list(region_xywh_precrop),
            left_px=DEFAULT_PRE_CROP_LEFT_PX,
            top_px=DEFAULT_PRE_CROP_TOP_PX,
        )
        region = tuple(int(round(float(v))) for v in rect_adj)
    except (TypeError, ValueError):
        return None
    scene = np.asarray(cropped_rgb.convert("RGB"))
    if scene.ndim != 3 or scene.shape[2] != 3:
        return None
    r = _match_template_in_roi(scene, region, tpl_rgb)
    if r is None:
        return None
    _x, _y, _w, _h, conf = r
    if conf < float(threshold):
        return None
    return r


# 与 `auto_fish_executor._page_reeling` 同一 ROI 与阈值；整窗未裁坐标系 [x, y, w, h]
REELING_BAR_MATCH_THRESHOLD = 0.8
REELING_BAR_REGION_PRECROP = (402.72, 94.16, 484.61, 16.58)
# 刻度：在整窗未裁 y = 溜鱼条 y + h/2 的**单行**上按 RGB 扫 x，颜色约 #FEF7A5；返回框 w=1,h=1 便于 scale_cx。
REELING_SCALE_COLOR_RGB_LOW = (238, 228, 130)
REELING_SCALE_COLOR_RGB_HIGH = (255, 255, 220)
REELING_SCALE_COLOR_MIN_CONF = 0.5
_REELING_BAR_EDGE_TEMPLATE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("left", "溜鱼条-左边缘.png", "左边缘"),
    ("right", "溜鱼条-右边缘.png", "右边缘"),
)


def _detect_reeling_scale_by_color(
    cropped_rgb: Image.Image,
) -> tuple[int, int, int, int, float] | None:
    """在整窗未裁坐标系溜鱼条竖直中心那一行（映射到裁剪图 y）上，按 RGB 范围在 ROI 水平范围内找刻度 x。"""
    scene = np.asarray(cropped_rgb.convert("RGB"))
    if scene.ndim != 3 or scene.shape[2] != 3:
        return None
    ih, iw = int(scene.shape[0]), int(scene.shape[1])
    if ih < 1 or iw < 1:
        return None
    try:
        xp, yp, wp, hp = (
            float(REELING_BAR_REGION_PRECROP[0]),
            float(REELING_BAR_REGION_PRECROP[1]),
            float(REELING_BAR_REGION_PRECROP[2]),
            float(REELING_BAR_REGION_PRECROP[3]),
        )
        y_line_precrop = yp + hp / 2.0
        rect_adj = _apply_pre_crop_offset(
            [xp, yp, wp, hp],
            left_px=DEFAULT_PRE_CROP_LEFT_PX,
            top_px=DEFAULT_PRE_CROP_TOP_PX,
        )
        region = tuple(int(round(float(v))) for v in rect_adj)
        y_row = int(round(y_line_precrop - float(DEFAULT_PRE_CROP_TOP_PX)))
    except (TypeError, ValueError):
        return None
    rx, _ry, rw, _rh = region
    if rw <= 0:
        return None
    y_row = max(0, min(ih - 1, y_row))
    x0 = max(0, rx)
    x1 = min(iw, rx + rw)
    if x1 <= x0:
        return None
    row = scene[y_row : y_row + 1, x0:x1, :].reshape(-1, 3)
    lo = np.array(REELING_SCALE_COLOR_RGB_LOW, dtype=np.uint8)
    hi = np.array(REELING_SCALE_COLOR_RGB_HIGH, dtype=np.uint8)
    mask = np.all((row >= lo) & (row <= hi), axis=1).astype(np.float64)
    peak = float(mask.max()) if mask.size else 0.0
    if peak <= 0.0:
        return None
    thr = peak * 0.45
    xs = np.flatnonzero(mask >= thr)
    if xs.size == 0:
        xs = np.array([int(np.argmax(mask))], dtype=np.int64)
        wts = mask[xs]
    else:
        wts = mask[xs]
    cx_rel = float(np.sum(xs * wts) / np.sum(wts))
    conf = min(1.0, peak)
    if conf < float(REELING_SCALE_COLOR_MIN_CONF):
        return None
    cx = int(round(x0 + cx_rel))
    cx = max(x0, min(x1 - 1, cx))
    return (cx, int(y_row), 1, 1, float(conf))


def run_reeling_bar_templates(
    cropped_rgb: Image.Image,
) -> tuple[dict[str, object], tuple[tuple[int, int, int, int, float] | None, tuple[int, int, int, int, float] | None, tuple[int, int, int, int, float] | None]]:
    """正在溜鱼页：在溜鱼条 ROI 内匹配左/右边缘；刻度在条带竖直中心单行上按浅黄 (#FEF7A5) 扫 x。返回 ``(API 可序列化 debug, (左,右,刻度) 三元组)``。"""
    base = Path(__file__).resolve().parents[1] / "images" / "auto_fish"
    t0 = time.perf_counter()
    trips: list[tuple[int, int, int, int, float] | None] = []
    items: list[dict[str, object]] = []
    for key, fn, zh_label in _REELING_BAR_EDGE_TEMPLATE_ROWS:
        path = base / fn
        r = match_template_in_precrop_roi(
            cropped_rgb,
            path,
            REELING_BAR_REGION_PRECROP,
            threshold=float(REELING_BAR_MATCH_THRESHOLD),
        )
        trips.append(r)
        if r is None:
            items.append({"key": key, "label": zh_label, "similarity": None})
        else:
            x, y, w, h, conf = r
            items.append(
                {
                    "key": key,
                    "label": zh_label,
                    "x": int(x),
                    "y": int(y),
                    "w": int(w),
                    "h": int(h),
                    "similarity": float(conf),
                }
            )
    scale_r = _detect_reeling_scale_by_color(cropped_rgb)
    trips.append(scale_r)
    if scale_r is None:
        items.append({"key": "scale", "label": "刻度", "method": "color", "similarity": None})
    else:
        sx, sy, sw, sh, sc = scale_r
        items.append(
            {
                "key": "scale",
                "label": "刻度",
                "method": "color",
                "x": int(sx),
                "y": int(sy),
                "w": int(sw),
                "h": int(sh),
                "similarity": float(sc),
            }
        )
    ms = (time.perf_counter() - t0) * 1000.0
    debug: dict[str, object] = {"match_ms": round(ms, 3), "items": items}
    return (debug, (trips[0], trips[1], trips[2]))


def _eval_page_features(
    feats: list[_FeatureTemplate],
    scene: np.ndarray,
    th_val: float,
) -> tuple[int, int, int, int, float] | None:
    """单页：多特征中取 TM_CCOEFF_NORMED 过阈值且置信度最高的一条；成功返回 (bx, by, bw, bh, confidence)。"""
    if not feats:
        return None

    best: tuple[int, int, int, int, float] | None = None
    for ft in feats:
        r = _match_template_in_roi(scene, ft.region_cropped, ft.tpl_rgb)
        if r is None:
            continue
        x_, y_, w_, h_, conf = r
        if conf < th_val:
            continue
        if best is None or conf > best[4]:
            best = (x_, y_, w_, h_, conf)
    return best


class PageTemplateMatcher:
    """懒加载配置与模板；`match` 按 `_pages_ordered` 顺序短路。线程安全仅当单线程调用。"""

    def __init__(self, pages_json: Path | None = None) -> None:
        self._path = pages_json or DEFAULT_PAGES_JSON
        self._threshold = DEFAULT_MATCH_THRESHOLD
        self._loaded = False
        # 加载完成后按 page_priority 排好序的 (id, label, features)
        self._pages_ordered: list[tuple[str, str, list[_FeatureTemplate]]] = []

    def _ensure_loaded(self) -> None:
        """懒加载：读 `page_priority` 与 `pages`，填充 `_pages_ordered`。"""
        if self._loaded:
            return
        self._loaded = True
        self._pages_ordered = []
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        base = self._path.parent
        raw_pri = data.get("page_priority") if isinstance(data, dict) else None
        pri_tokens = [s for x in raw_pri if (s := str(x).strip())] if isinstance(raw_pri, list) else []
        pages = data.get("pages") if isinstance(data, dict) else None
        if not isinstance(pages, list):
            return
        loaded: dict[str, tuple[str, list[_FeatureTemplate]]] = {}
        for p in pages:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "")
            if not pid:
                continue
            label = str(p.get("label") or pid or "unknown")
            feats = p.get("features")
            if not isinstance(feats, list):
                continue
            tpl_entries: list[_FeatureTemplate] = []
            for f in feats:
                if not isinstance(f, dict):
                    continue
                fn = f.get("file")
                if not isinstance(fn, str) or not fn.strip():
                    continue
                fp = (base / fn).resolve()
                if not fp.is_file():
                    continue
                try:
                    im = Image.open(fp).convert("RGB")
                    arr = np.asarray(im)
                except OSError:
                    continue
                if arr.ndim != 3 or arr.shape[2] != 3:
                    continue
                rect = f.get("region")
                if not isinstance(rect, list) or len(rect) != 4:
                    continue
                # pages.json 的 region 基于“未裁剪前整窗截图”，需要先减去捕获侧默认裁剪量
                try:
                    rect_adj = _apply_pre_crop_offset(
                        rect,
                        left_px=DEFAULT_PRE_CROP_LEFT_PX,
                        top_px=DEFAULT_PRE_CROP_TOP_PX,
                    )
                    rx, ry, rw, rh = (int(round(float(v))) for v in rect_adj)
                except (TypeError, ValueError):
                    continue
                th_tpl, tw_tpl = int(arr.shape[0]), int(arr.shape[1])
                if tw_tpl > rw or th_tpl > rh:
                    continue
                tpl_entries.append(
                    _FeatureTemplate(
                        region_cropped=(rx, ry, rw, rh),
                        tpl_rgb=arr,
                    )
                )
            # 仅保留至少有一个可用特征的页面
            if tpl_entries:
                loaded[pid] = (label, tpl_entries)

        # page_priority 支持写 label 或 id：构建反向映射用于解析与排序
        label_to_pid: dict[str, str] = {}
        for pid, (lab, _feats) in loaded.items():
            if lab and lab not in label_to_pid:
                label_to_pid[lab] = pid

        priority_rank: dict[str, int] = {}
        rank = 0
        for tok in pri_tokens:
            rid = label_to_pid.get(tok)
            if rid is None and tok in loaded:
                rid = tok
            if rid is None or rid in priority_rank:
                continue
            priority_rank[rid] = rank
            rank += 1
        pri_fb = len(priority_rank) + 10_000
        self._pages_ordered = [
            (pid, lab, fts)
            for pid, (lab, fts) in sorted(
                loaded.items(),
                key=lambda it: (priority_rank.get(it[0], pri_fb), it[0]),
            )
        ]

    def get_match_threshold(self) -> float:
        """TM_CCOEFF_NORMED 判定下限，约 [0,1]。"""
        return float(self._threshold)

    def set_match_threshold(self, value: float) -> float:
        """限定在 [0,1]，返回钳制后的值。"""
        v = float(value)
        v = max(0.0, min(v, 1.0))
        self._threshold = v
        return v

    def reload(self) -> None:
        """强制下次 `match` 重新读盘（优先级、模板等均重载）。"""
        self._loaded = False
        self._pages_ordered = []
        self._ensure_loaded()

    def match(self, cropped_rgb: Image.Image) -> PageMatchResult | None:
        """在各特征的 region ROI 内对整张模板 PNG 做匹配；矩形为裁剪坐标系像素。"""
        self._ensure_loaded()
        if not self._pages_ordered:
            return None
        cw, ch = cropped_rgb.size
        # 过小图像无法稳定做模板相关匹配，避免无意义计算
        if cw < 8 or ch < 8:
            return None

        # 统一为 RGB 的 H×W×3 uint8，与特征评估函数约定一致
        scene = np.asarray(cropped_rgb.convert("RGB"))
        if scene.ndim != 3 or scene.shape[2] != 3:
            return None
        th_val = self._threshold

        for pid, label, feats in self._pages_ordered:
            box = _eval_page_features(feats, scene, th_val)
            if box is None:
                continue
            bx, by, bw, bh, conf = box
            return PageMatchResult(
                page_id=pid,
                label=label,
                confidence=float(conf),
                x=int(bx),
                y=int(by),
                w=int(bw),
                h=int(bh),
            )
        return None
