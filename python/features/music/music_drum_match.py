# -*- coding: utf-8 -*-
"""超强音敲鼓：四槽 ROI + `鼓中心-{n}.png` 模板匹配，产出前端叠加框用的调试结构。"""

from __future__ import annotations

from typing import Any

from PIL import Image

from app_paths import python_pkg_root
import tools.game_input as game_input
from tools.page_template_match import (
    DEFAULT_PRE_CROP_LEFT_PX,
    DEFAULT_PRE_CROP_TOP_PX,
    match_template_score_in_precrop_roi,
)

MUSIC_IMG_DIR = python_pkg_root() / "images" / "music"

# 整窗未裁坐标系 [x, y, w, h]；与 `page.json` 的 region 约定一致
DRUM_ROI_PRECROP: tuple[tuple[float, float, float, float], ...] = (
    (263.0, 579.0, 67.0, 66.0),
    (488.0, 579.0, 67.0, 66.0),
    (729.0, 579.0, 67.0, 66.0),
    (953.0, 579.0, 67.0, 66.0),
)
DRUM_TEMPLATE_NAMES: tuple[str, ...] = (
    "鼓中心-1.png",
    "鼓中心-2.png",
    "鼓中心-3.png",
    "鼓中心-4.png",
)
# 与 `game_input` 中 Virtual-Key 一致，供执行器发键与 JSON 透传
DRUM_VK: tuple[int, int, int, int] = (
    game_input.VK_D,
    game_input.VK_F,
    game_input.VK_J,
    game_input.VK_K,
)
DRUM_LABELS: tuple[str, ...] = ("D", "F", "J", "K")
DRUM_KEYS: tuple[str, ...] = ("d1", "d2", "d3", "d4")


def _fallback_roi_box(roi_precrop: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x, y, w, h = roi_precrop
    rx = float(x) - float(DEFAULT_PRE_CROP_LEFT_PX)
    ry = float(y) - float(DEFAULT_PRE_CROP_TOP_PX)
    return (
        int(round(rx)),
        int(round(ry)),
        int(round(float(w))),
        int(round(float(h))),
    )


def compute_music_drum_debug(cropped_rgb: Image.Image) -> dict[str, Any]:
    """对四槽 ROI 算相似度；矩形固定为各 ROI 映射到裁剪坐标系，仅 `similarity` 随帧变化。"""
    items: list[dict[str, Any]] = []
    for i, roi_precrop in enumerate(DRUM_ROI_PRECROP):
        key = DRUM_KEYS[i]
        label = DRUM_LABELS[i]
        vk = DRUM_VK[i]
        tpl_name = DRUM_TEMPLATE_NAMES[i]
        tpl_path = MUSIC_IMG_DIR / tpl_name
        bx, by, bw, bh = _fallback_roi_box(roi_precrop)

        similarity: float | None = None
        if tpl_path.is_file():
            raw_score = match_template_score_in_precrop_roi(cropped_rgb, tpl_path, roi_precrop)
            if raw_score is not None:
                similarity = float(raw_score)

        items.append(
            {
                "key": key,
                "label": label,
                "vk": vk,
                "x": bx,
                "y": by,
                "w": bw,
                "h": bh,
                "similarity": similarity,
            }
        )

    return {"items": items}

