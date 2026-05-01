# -*- coding: utf-8 -*-
"""根据 `images/auto_fish/pages.json` 与模板 PNG，对裁剪后的游戏画面做 OpenCV 模板匹配。"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

DEFAULT_PAGES_JSON = Path(__file__).resolve().parent / "images" / "auto_fish" / "pages.json"
DEFAULT_MATCH_THRESHOLD = 0.5
# pages.json 的 region 基于“未裁剪前整窗截图”的坐标；捕获时会默认裁掉这些边缘。
DEFAULT_PRE_CROP_TOP_PX = 52
DEFAULT_PRE_CROP_LEFT_PX = 2


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
class PageMatchEnvelope:
    """`result` 为当前帧择优后的整页匹配；`template_debug` 为配置了 `features[].debug=true` 的模板调试快照。"""

    result: PageMatchResult | None
    template_debug: tuple[dict[str, object], ...] = ()


def _rgb_to_jpeg_base64(rgb: np.ndarray, *, quality: int = 82) -> str:
    """RGB uint8 HxWx3 → JPEG Base64 ASCII；失败返回空串。"""
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.size == 0:
        return ""
    try:
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    except Exception:
        return ""
    if not ok or buf is None:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")


@dataclass(frozen=True)
class _FeatureTemplate:
    """`region_cropped` 为游戏画面裁剪坐标系下的搜索矩形；`tpl_rgb` 为整张模板 PNG（在 ROI 内匹配）。"""

    region_cropped: tuple[int, int, int, int]
    tpl_rgb: np.ndarray
    template_file: str
    debug: bool


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


def _match_one_feature(
    scene_rgb: np.ndarray,
    tpl_rgb: np.ndarray,
) -> tuple[int, int, int, int, float] | None:
    sh, sw = scene_rgb.shape[:2]
    th, tw = tpl_rgb.shape[:2]
    if th > sh or tw > sw or th < 1 or tw < 1:
        return None

    res = cv2.matchTemplate(scene_rgb, tpl_rgb, cv2.TM_CCOEFF_NORMED)
    _min_v, max_v, _min_loc, max_loc = cv2.minMaxLoc(res)
    mx, my = max_loc
    return (mx, my, tw, th, float(max_v))


def _match_template_in_roi(
    scene_rgb: np.ndarray,
    region: tuple[int, int, int, int],
    tpl_rgb: np.ndarray,
) -> tuple[int, int, int, int, float] | None:
    """在 `scene_rgb` 的 region ROI 内对 `tpl_rgb` 做模板匹配；返回 (全局 x, 全局 y, w, h, score)。"""
    rx, ry, rw, rh = region
    roi = _crop_rgb_by_rect(scene_rgb, region)
    if roi is None:
        return None
    loc = _match_one_feature(roi, tpl_rgb)
    if loc is None:
        return None
    mx, my, tw, th, cf = loc
    return (rx + mx, ry + my, tw, th, cf)


class PageTemplateMatcher:
    """懒加载配置与模板；`match` 线程安全仅当单线程调用（当前由捕获线程独占）。"""

    def __init__(self, pages_json: Path | None = None) -> None:
        self._path = pages_json or DEFAULT_PAGES_JSON
        self._threshold = DEFAULT_MATCH_THRESHOLD
        self._pre_crop_top_px = DEFAULT_PRE_CROP_TOP_PX
        self._pre_crop_left_px = DEFAULT_PRE_CROP_LEFT_PX
        self._loaded = False
        # `page_priority` 反向映射：pid -> rank（越小越优先）
        self._priority_rank: dict[str, int] = {}
        # pid -> (label, match_mode, features[])
        self._templates_by_pid: dict[str, tuple[str, str, list[_FeatureTemplate]]] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.is_file():
            self._priority_rank = {}
            self._templates_by_pid = {}
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._priority_rank = {}
            self._templates_by_pid = {}
            return
        base = self._path.parent
        raw_pri = data.get("page_priority") if isinstance(data, dict) else None
        pri_tokens: list[str] = []
        if isinstance(raw_pri, list):
            for x in raw_pri:
                s = str(x).strip()
                if s:
                    pri_tokens.append(s)
        pages = data.get("pages") if isinstance(data, dict) else None
        if not isinstance(pages, list):
            self._templates_by_pid = {}
            return
        loaded: dict[str, tuple[str, str, list[_FeatureTemplate]]] = {}
        for p in pages:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "")
            if not pid:
                continue
            label = str(p.get("label") or pid or "unknown")
            mode = str(p.get("match_mode") or "any").lower()
            if mode not in ("any", "all"):
                mode = "any"
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
                # 以对齐 `CaptureService` 传入的 cropped_rgb 坐标系。
                try:
                    rect_adj = _apply_pre_crop_offset(
                        rect,
                        left_px=self._pre_crop_left_px,
                        top_px=self._pre_crop_top_px,
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
                        template_file=str(fn).strip(),
                        debug=bool(f.get("debug")),
                    )
                )
            if tpl_entries:
                loaded[pid] = (label, mode, tpl_entries)
        self._templates_by_pid = loaded

        # page_priority 支持写 label 或 id：构建反向映射用于解析与排序
        label_to_pid: dict[str, str] = {}
        for pid, (lab, _mode, _feats) in loaded.items():
            if lab and lab not in label_to_pid:
                label_to_pid[lab] = pid

        priority_rank: dict[str, int] = {}
        rank = 0
        for tok in pri_tokens:
            rid: str | None
            if tok in label_to_pid:
                rid = label_to_pid[tok]
            elif tok in loaded:
                rid = tok
            else:
                rid = None
            if rid is None or rid in priority_rank:
                continue
            priority_rank[rid] = rank
            rank += 1
        self._priority_rank = priority_rank

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
        self._priority_rank = {}
        self._templates_by_pid = {}
        self._ensure_loaded()

    def match(self, cropped_rgb: Image.Image) -> PageMatchEnvelope | None:
        """在各特征的 region ROI 内对整张模板 PNG 做匹配；矩形为裁剪坐标系像素；附带 `debug` 特征快照。"""
        self._ensure_loaded()
        if not self._templates_by_pid:
            return None
        cw, ch = cropped_rgb.size
        if cw < 8 or ch < 8:
            return None

        scene = np.asarray(cropped_rgb.convert("RGB"))
        if scene.ndim != 3 or scene.shape[2] != 3:
            return None
        th_val = self._threshold

        dbg_rows: list[dict[str, object]] = []
        for pid, (label, _mode, feats) in self._templates_by_pid.items():
            for ft in feats:
                if not ft.debug:
                    continue
                rx, ry, rw, rh = ft.region_cropped
                roi = _crop_rgb_by_rect(scene, ft.region_cropped)
                mt = _match_template_in_roi(scene, ft.region_cropped, ft.tpl_rgb)
                sim = float(mt[4]) if mt else 0.0
                dbg_rows.append(
                    {
                        "page_id": pid,
                        "page_label": label,
                        "template_file": ft.template_file,
                        "similarity": sim,
                        "region": [int(rx), int(ry), int(rw), int(rh)],
                        "roi_jpeg_base64": _rgb_to_jpeg_base64(roi) if roi is not None else "",
                        "template_jpeg_base64": _rgb_to_jpeg_base64(ft.tpl_rgb),
                    }
                )
        dbg_tuple = tuple(dbg_rows)

        def _rank(pg_id: str) -> int:
            # 未出现在 priority 中的页面视作最低优先级
            return self._priority_rank.get(pg_id, len(self._priority_rank) + 10_000)

        candidates: list[tuple[float, str, str, int, int, int, int]] = []

        for pid, (label, mode, feats) in self._templates_by_pid.items():
            if mode == "all":
                per: list[tuple[int, int, int, int, float]] = []
                ok = True
                for ft in feats:
                    r = _match_template_in_roi(scene, ft.region_cropped, ft.tpl_rgb)
                    if r is None or r[4] < th_val:
                        ok = False
                        break
                    per.append(r)
                if not ok or len(per) != len(feats):
                    continue
                xs = [h[0] for h in per]
                ys = [h[1] for h in per]
                xe = [h[0] + h[2] for h in per]
                ye = [h[1] + h[3] for h in per]
                ux0, uy0, ux1, uy1 = min(xs), min(ys), max(xe), max(ye)
                uconf = min(h[4] for h in per)
                bx, by, bw, bh = ux0, uy0, ux1 - ux0, uy1 - uy0
                cand = (uconf, pid, label, bx, by, bw, bh)
            else:
                hits: list[tuple[int, int, int, int, float]] = []
                for ft in feats:
                    r = _match_template_in_roi(scene, ft.region_cropped, ft.tpl_rgb)
                    if r is None:
                        continue
                    x_, y_, w_, h_, conf = r
                    if conf >= th_val:
                        hits.append((x_, y_, w_, h_, conf))
                if not hits:
                    continue
                bx, by, bw, bh, uconf = max(hits, key=lambda t: t[4])
                cand = (uconf, pid, label, bx, by, bw, bh)

            candidates.append(cand)

        if not candidates:
            if not dbg_tuple:
                return None
            return PageMatchEnvelope(result=None, template_debug=dbg_tuple)

        # 先看 `page_priority` 顺序（越靠前越高），同级再取置信度最高
        _conf, pid, label, bx, by, bw, bh = min(
            candidates,
            key=lambda c: (_rank(c[1]), -c[0]),
        )
        return PageMatchEnvelope(
            result=PageMatchResult(
                page_id=pid,
                label=label,
                confidence=float(_conf),
                x=int(bx),
                y=int(by),
                w=int(bw),
                h=int(bh),
            ),
            template_debug=dbg_tuple,
        )
