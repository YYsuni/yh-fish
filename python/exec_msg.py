# -*- coding: utf-8 -*-
"""执行过程文本输出：内存环形缓冲，供 GET /api/msg/log 拉取。"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_MAX = 400
_lines: deque[tuple[float, str]] = deque(maxlen=_MAX)
_lock = threading.Lock()


def msg_out(text: str) -> None:
    with _lock:
        _lines.append((time.time(), text))


def snapshot() -> list[dict[str, Any]]:
    with _lock:
        return [{"t": t, "m": m} for t, m in _lines]
