# -*- coding: utf-8 -*-
"""捕获管线调试：各步耗时（毫秒）键名与合并逻辑，供 `capture_service` 与 API/WS 对齐。"""

from __future__ import annotations

import time

# 与前端 `capture-pipeline-debug.ts` 的 PIPELINE_KEYS 保持一致。
PIPELINE_TIMING_KEYS: tuple[str, ...] = (
    "find_hwnd_ms",
    "decode_ms",
    "template_match_ms",
    "scale_encode_ms",
)


def empty_pipeline_timings() -> dict[str, float]:
    """各步骤占位 0，便于合并部分路径的实测值。"""
    return {k: 0.0 for k in PIPELINE_TIMING_KEYS}


def merge_pipeline_timings(partial: dict[str, float]) -> dict[str, float]:
    """将 partial 合并进完整键表，未知键丢弃。"""
    out = empty_pipeline_timings()
    for k, v in partial.items():
        if k in out and isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def perf_elapsed_ms(t0: float) -> float:
    """自 `t0 = time.perf_counter()` 起经历的毫秒数。"""
    return (time.perf_counter() - t0) * 1000.0
