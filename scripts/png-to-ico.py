# -*- coding: utf-8 -*-
"""从 PNG 生成多尺寸 ICO，供 PyInstaller / Inno Setup 使用。"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: png-to-ico.py <input.png> <output.ico>", file=sys.stderr)
        sys.exit(2)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    im.save(dst, format="ICO", sizes=sizes)


if __name__ == "__main__":
    main()
