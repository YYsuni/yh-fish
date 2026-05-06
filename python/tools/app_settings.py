# -*- coding: utf-8 -*-
"""应用设置：快捷键、点击校准等；读写 ``app-settings.json``（兼容旧 ``hotkeys.json``）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class HotkeyPayload(BaseModel):
    key: str | None = None
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    meta: bool = False


class AppSettingsPayload(BaseModel):
    """应用设置：全局快捷键 + 物理点击坐标校准（整窗换算为客户区后再加上 ``click_offset_*``；写入 ``app-settings.json``）。"""

    model_config = ConfigDict(extra="ignore")

    start: HotkeyPayload
    stop: HotkeyPayload
    click_offset_x: int = 0
    click_offset_y: int = 0

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_click_offsets(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "click_offset_x" not in d and "wgc_precrop_offset_x" in d:
            d["click_offset_x"] = d.get("wgc_precrop_offset_x", 0)
        if "click_offset_y" not in d and "wgc_precrop_offset_y" in d:
            d["click_offset_y"] = d.get("wgc_precrop_offset_y", 0)
        d.pop("wgc_precrop_offset_x", None)
        d.pop("wgc_precrop_offset_y", None)
        return d


def default_app_settings() -> AppSettingsPayload:
    return AppSettingsPayload(
        start=HotkeyPayload(key=None, ctrl=False, shift=False, alt=False, meta=False),
        stop=HotkeyPayload(key="F12", ctrl=False, shift=False, alt=False, meta=False),
        click_offset_x=0,
        click_offset_y=0,
    )


def app_settings_path(*, base_dir: Path) -> Path:
    return base_dir / "app-settings.json"


def _legacy_hotkeys_json_path(*, base_dir: Path) -> Path:
    return base_dir / "hotkeys.json"


def load_app_settings(*, base_dir: Path) -> AppSettingsPayload:
    p = app_settings_path(base_dir=base_dir)
    legacy = _legacy_hotkeys_json_path(base_dir=base_dir)
    if p.exists():
        try:
            data = json.loads(p.read_text("utf-8"))
            return AppSettingsPayload.model_validate(data)
        except Exception:
            return default_app_settings()
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text("utf-8"))
            out = AppSettingsPayload.model_validate(data)
            save_app_settings(base_dir=base_dir, settings=out)
            return out
        except Exception:
            return default_app_settings()
    return default_app_settings()


def save_app_settings(*, base_dir: Path, settings: AppSettingsPayload) -> None:
    p = app_settings_path(base_dir=base_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(p)
    legacy = _legacy_hotkeys_json_path(base_dir=base_dir)
    if legacy.exists():
        try:
            legacy.unlink()
        except OSError:
            pass
