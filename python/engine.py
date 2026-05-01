# -*- coding: utf-8 -*-

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal

State = Literal["idle", "running", "stopped", "error"]


@dataclass
class Status:
    state: State = "idle"
    message: str = ""
    tick: int = 0


class FishingEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._st = Status()

    def _set(self, state: State, message: str = "", *, tick: int | None = None) -> None:
        with self._lock:
            self._st.state = state
            self._st.message = message
            if tick is not None:
                self._st.tick = tick

    def get_status_dict(self) -> dict:
        with self._lock:
            return {"state": self._st.state, "message": self._st.message, "tick": self._st.tick}

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
        self._stop.clear()
        self._set("running", "占位循环", tick=0)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        self._set("stopped", "已停止")

    def _loop(self) -> None:
        try:
            n = 0
            while not self._stop.is_set():
                n += 1
                self._set("running", "等待接入截图 / OpenCV", tick=n)
                time.sleep(0.5)
            self._set("idle", "空闲")
        except Exception as e:  # noqa: BLE001
            self._set("error", str(e))
