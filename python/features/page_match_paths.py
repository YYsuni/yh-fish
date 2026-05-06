# -*- coding: utf-8 -*-
"""页面模板配置 JSON 的磁盘路径集中声明。"""

from __future__ import annotations

from pathlib import Path

from app_paths import python_pkg_root

AUTO_FISH_PAGES_JSON: Path = python_pkg_root() / "images" / "auto_fish" / "pages.json"
MUSIC_PAGES_JSON: Path = python_pkg_root() / "images" / "music" / "page.json"
MANAGER_PAGES_JSON: Path = python_pkg_root() / "images" / "manager" / "page.json"

