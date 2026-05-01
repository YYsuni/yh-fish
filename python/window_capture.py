# -*- coding: utf-8 -*-
"""Windows：按标题正则匹配顶层可见窗口，返回 HWND（供 WGC 使用）。"""

from __future__ import annotations

import re
import sys

if sys.platform != "win32":

    def find_game_hwnd(title_regex: str) -> int | None:  # noqa: ARG001
        return None

else:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _title(hwnd: int) -> str:
        n = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(n)
        user32.GetWindowTextW(hwnd, buf, n)
        return buf.value or ""

    def find_game_hwnd(title_regex: str) -> int | None:
        pat = re.compile(title_regex)
        found: list[int] = []

        def cb(hwnd: int, _l: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            t = _title(hwnd).strip()
            if pat.match(t):
                found.append(hwnd)
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return found[0] if found else None
