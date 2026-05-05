# -*- coding: utf-8 -*-
"""钓鱼 / 超强音页面模板配置的磁盘路径。

通用匹配算法见 `page_template_match.PageTemplateMatcher`；此处仅集中声明各功能使用的 `pages.json` / `page.json` 位置。"""
from __future__ import annotations

from pathlib import Path

from app_paths import python_pkg_root

AUTO_FISH_PAGES_JSON: Path = python_pkg_root() / "images" / "auto_fish" / "pages.json"
MUSIC_PAGES_JSON: Path = python_pkg_root() / "images" / "music" / "page.json"
