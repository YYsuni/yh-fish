# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class HotkeyPayload(BaseModel):
    key: str | None = None
    ctrl: bool = False
    shift: bool = False
    alt: bool = False
    meta: bool = False


class HotkeysPayload(BaseModel):
    start: HotkeyPayload
    stop: HotkeyPayload


def default_hotkeys() -> HotkeysPayload:
    return HotkeysPayload(
        start=HotkeyPayload(key=None, ctrl=False, shift=False, alt=False, meta=False),
        stop=HotkeyPayload(key="F12", ctrl=False, shift=False, alt=False, meta=False),
    )


def hotkeys_path(*, base_dir: Path) -> Path:
    # 持久化文件放在 python/ 目录下，便于与 server.py 同级管理
    return base_dir / "hotkeys.json"


def load_hotkeys(*, base_dir: Path) -> HotkeysPayload:
    p = hotkeys_path(base_dir=base_dir)
    if not p.exists():
        return default_hotkeys()
    try:
        data = json.loads(p.read_text("utf-8"))
        return HotkeysPayload.model_validate(data)
    except Exception:
        return default_hotkeys()


def save_hotkeys(*, base_dir: Path, hotkeys: HotkeysPayload) -> None:
    p = hotkeys_path(base_dir=base_dir)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(hotkeys.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(p)

