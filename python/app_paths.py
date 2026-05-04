# -*- coding: utf-8 -*-
"""开发与 PyInstaller 冻结环境下的统一资源根路径。"""

from __future__ import annotations

import sys
from pathlib import Path


def python_pkg_root() -> Path:
    """含 `images/` 的目录（开发时即 `python/`）。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "python"
    return Path(__file__).resolve().parent
