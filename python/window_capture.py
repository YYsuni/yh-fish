# -*- coding: utf-8 -*-
"""Windows：按标题正则匹配游戏窗口，截取客户区为 JPEG。"""

from __future__ import annotations

import io
import re
import sys

if sys.platform != "win32":

    def find_game_hwnd(title_regex: str) -> int | None:  # noqa: ARG001
        return None

    def grab_client_jpeg(hwnd: int, quality: int = 72) -> tuple[bytes | None, int, int]:  # noqa: ARG001
        return None, 0, 0

else:
    import ctypes
    from ctypes import wintypes

    import mss
    from PIL import Image

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

    def _client_screen_box(hwnd: int) -> tuple[int, int, int, int] | None:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        pt = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return None
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return (pt.x, pt.y, w, h)

    def grab_client_jpeg(hwnd: int, quality: int = 72) -> tuple[bytes | None, int, int]:
        box = _client_screen_box(hwnd)
        if not box:
            return None, 0, 0
        left, top, w, h = box
        region = {"left": int(left), "top": int(top), "width": int(w), "height": int(h)}
        try:
            with mss.mss() as sct:
                shot = sct.grab(region)
                img = Image.frombytes("RGB", (shot.width, shot.height), shot.bgra, "raw", "BGRX")
        except (OSError, ValueError):
            return None, 0, 0
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue(), shot.width, shot.height
