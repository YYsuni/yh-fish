# -*- coding: utf-8 -*-
"""Windows：按标题正则匹配顶层可见窗口 HWND；计算标题栏裁切高度（供整窗捕获对齐）。"""

from __future__ import annotations

import re
import sys

if sys.platform != "win32":

    def find_game_hwnd(title_regex: str) -> int | None:  # noqa: ARG001
        """非 Windows 无 HWND，始终返回 None。"""
        return None

    def window_title_bar_crop_px(hwnd: int) -> int:  # noqa: ARG001
        """非 Windows 无窗口矩形，返回 0。"""
        return 0

else:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _title(hwnd: int) -> str:
        """读取窗口标题文本。"""
        n = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(n)
        user32.GetWindowTextW(hwnd, buf, n)
        return buf.value or ""

    def find_game_hwnd(title_regex: str) -> int | None:
        """枚举顶层可见窗口，返回首个标题匹配正则的 HWND。"""
        pat = re.compile(title_regex)
        found: list[int] = []

        def cb(hwnd: int, _l: int) -> bool:
            """`EnumWindows` 回调：收集匹配的 HWND。"""
            if not user32.IsWindowVisible(hwnd):
                return True
            t = _title(hwnd).strip()
            if pat.match(t):
                found.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return found[0] if found else None

    def window_title_bar_crop_px(hwnd: int) -> int:
        """从窗口外框顶到客户区顶部的像素高度（标题栏 + 顶边框），与 WGC 整窗帧对齐。"""
        hwnd = int(hwnd)
        outer = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(outer)):
            return 0
        pt = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return 0
        return max(0, int(pt.y - outer.top))
