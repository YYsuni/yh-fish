# -*- coding: utf-8 -*-
"""Windows：对 HWND PostMessage WM_KEYDOWN/WM_KEYUP，不置前。非 Windows 为空实现。"""

from __future__ import annotations

import sys

VK_F = 0x46

if sys.platform == "win32":
    import ctypes
    import random
    import time
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101

    def _lparam(vk: int, *, key_up: bool) -> int:
        scan = int(_user32.MapVirtualKeyW(vk & 0xFF, 0)) & 0xFF
        lp = 1 | ((scan & 0xFF) << 16)
        if key_up:
            lp |= 1 << 30 | 1 << 31
        return lp

    def _post_key(hwnd: int, vk: int, *, key_up: bool) -> None:
        if hwnd <= 0:
            return
        vk_i = int(vk) & 0xFF
        msg = WM_KEYUP if key_up else WM_KEYDOWN
        _user32.PostMessageW(wintypes.HWND(hwnd), msg, wintypes.WPARAM(vk_i), wintypes.LPARAM(_lparam(vk_i, key_up=key_up)))

    def send_key_tap(hwnd: int, vk: int) -> None:
        _post_key(hwnd, vk, key_up=False)
        time.sleep(random.uniform(0.04, 0.14))
        _post_key(hwnd, vk, key_up=True)

    def send_key_down(hwnd: int, vk: int) -> None:
        _post_key(hwnd, vk, key_up=False)

    def send_key_up(hwnd: int, vk: int) -> None:
        _post_key(hwnd, vk, key_up=True)

else:

    def send_key_tap(hwnd: int, vk: int) -> None:
        _ = hwnd, vk

    def send_key_down(hwnd: int, vk: int) -> None:
        _ = hwnd, vk

    def send_key_up(hwnd: int, vk: int) -> None:
        _ = hwnd, vk
