# -*- coding: utf-8 -*-

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from capture_service import CaptureService


class SetFpsBody(BaseModel):
    """POST `/api/capture/fps` 的请求体。"""

    fps: float = Field(ge=1, le=60)


def create_app(
    *,
    capture: CaptureService,
    serve_static: bool,
    dist_dir: Path,
) -> FastAPI:
    """组装 FastAPI：捕获相关 API，可选 SPA 静态目录。"""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """进程生命周期内启动/停止捕获后台线程。"""
        capture.start_background()
        yield
        capture.stop_background()

    app = FastAPI(title="yh-fish", version="0.1.0", lifespan=lifespan)
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8848",
        "http://localhost:8848",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/capture/status")
    def cap_status() -> dict[str, Any]:
        """返回窗口是否就绪、HWND、裁剪后尺寸、当前 FPS。"""
        s = capture.get_status()
        return {
            "ok": s.ok,
            "hwnd": s.hwnd,
            "width": s.width,
            "height": s.height,
            "fps": s.fps,
        }

    @app.post("/api/capture/fps")
    def cap_set_fps(body: SetFpsBody) -> dict[str, float]:
        """设置捕获循环与 MJPEG 推送的目标帧率（1–60）。"""
        return {"fps": capture.set_fps(body.fps)}

    @app.get("/api/capture/mjpeg")
    def cap_mjpeg() -> StreamingResponse:
        """multipart MJPEG 流，供前端 `<img>` 预览。"""
        boundary = b"frame"

        def gen():
            """按当前 FPS 间隔推送 JPEG 分片。"""
            while True:
                chunk = capture.get_jpeg()
                yield b"--" + boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + chunk + b"\r\n"
                time.sleep(capture.mjpeg_sleep_s())

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    if serve_static and dist_dir.is_dir():
        index = dist_dir / "index.html"

        @app.get("/{full_path:path}")
        def spa(full_path: str) -> FileResponse:
            """存在文件则直接返回，否则回落到 `index.html`（SPA）。"""
            f = dist_dir / full_path
            return FileResponse(f) if f.is_file() else FileResponse(index)

    return app
