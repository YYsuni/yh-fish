# -*- coding: utf-8 -*-
"""Windows：按标题正则匹配顶层可见窗口 HWND；计算标题栏裁切高度（供整窗捕获对齐）。"""

from __future__ import annotations

import re
import sys

# WGC 整帧 JPEG 与 `capture_service._decode_and_crop_rgb`、`pages.json`「整窗未裁」坐标系对齐的边距（像素）。
WGC_SNAPSHOT_MARGIN_LR_PX = 2
WGC_SNAPSHOT_MARGIN_BOTTOM_PX = 2

if sys.platform != "win32":

    def find_game_hwnd(title_regex: str) -> int | None:  # noqa: ARG001
        """非 Windows 无 HWND，始终返回 None；按冷却间隔写入 exec_msg 日志。"""
        from tools.exec_msg import maybe_warn_non_windows_game_hwnd

        maybe_warn_non_windows_game_hwnd()
        return None

    def window_title_bar_crop_px(hwnd: int) -> int:  # noqa: ARG001
        """非 Windows 无窗口矩形，返回 0。"""
        return 0

else:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()

    from tools.exec_msg import msg_out

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    _dumped_visible_titles_once = False

    def _title(hwnd: int) -> str:
        """读取窗口标题文本。"""
        n = user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(n)
        user32.GetWindowTextW(hwnd, buf, n)
        return buf.value or ""

    def find_game_hwnd(title_regex: str) -> int | None:
        """枚举顶层可见窗口，返回首个标题匹配正则的 HWND（命中即停止枚举）。"""
        global _dumped_visible_titles_once

        pat = re.compile(title_regex)
        out: list[int] = []

        # 进程内首次调用时会向 exec_msg 打印一轮「可见顶层窗口」的 HWND 与标题，便于对照正则。
        if not _dumped_visible_titles_once:

            def dump_cb(hwnd: int, _l: int) -> bool:
                if not user32.IsWindowVisible(hwnd):
                    return True
                title = _title(hwnd).strip()
                if pat.match(title):
                    msg_out("成功捕获异环窗口ID")
                return True

            user32.EnumWindows(WNDENUMPROC(dump_cb), 0)
            _dumped_visible_titles_once = True

        def cb(hwnd: int, _l: int) -> bool:
            """`EnumWindows` 回调：取第一个匹配窗口后返回 False 结束枚举。"""
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _title(hwnd).strip()
            if pat.match(title):
                out.append(hwnd)
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out[0] if out else None

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


def wgc_precrop_xy_to_client(hwnd: int, precrop_x: int, precrop_y: int) -> tuple[int, int]:
    """将 WGC 整帧（含标题栏与左右约 ``WGC_SNAPSHOT_MARGIN_LR_PX`` 阴影带）像素坐标转为 HWND 客户区坐标。

    与 ``capture_service._decode_and_crop_rgb`` 的裁切一致：左减 ``WGC_SNAPSHOT_MARGIN_LR_PX``，上减
    ``window_title_bar_crop_px``。供 ``game_input.send_left_click_physical`` 等需 ``ClientToScreen`` 的路径在
    传入「整窗截图」坐标前先调用。
    """
    h = int(hwnd)
    top = window_title_bar_crop_px(h)
    return (int(precrop_x) - WGC_SNAPSHOT_MARGIN_LR_PX, int(precrop_y) - top)
