# -*- coding: utf-8 -*-

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from capture_service import CaptureService
from engine import FishingEngine


class CaptureConfigBody(BaseModel):
    title_regex: str | None = Field(default=None)


def create_app(
    *,
    engine: FishingEngine,
    capture: CaptureService,
    serve_static: bool,
    dist_dir: Path,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        capture.start_background()
        yield
        capture.stop_background()

    app = FastAPI(title="yh-fish", version="0.1.0", lifespan=lifespan)
    origins = ["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8848", "http://localhost:8848"]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "version": "0.1.0"}

    @app.get("/api/runtime/status")
    def status() -> dict:
        return engine.get_status_dict()

    @app.post("/api/runtime/start")
    def start() -> dict:
        ok = engine.start()
        return {"accepted": ok, "already_running": not ok}

    @app.post("/api/runtime/stop")
    def stop() -> dict:
        engine.stop()
        return {"accepted": True}

    @app.get("/api/capture/status")
    def cap_status() -> dict[str, Any]:
        s = capture.get_status()
        return {
            "ok": s.ok,
            "title_regex": s.title_regex,
            "hwnd": s.hwnd,
            "width": s.width,
            "height": s.height,
            "fps": s.fps,
            "message": s.message,
        }

    @app.post("/api/capture/config")
    def cap_config(body: CaptureConfigBody) -> dict[str, str]:
        if body.title_regex and body.title_regex.strip():
            capture.set_title_regex(body.title_regex.strip())
        return {"title_regex": capture.title_regex}

    @app.get("/api/capture/mjpeg")
    def cap_mjpeg() -> StreamingResponse:
        boundary = b"frame"

        def gen():
            while True:
                chunk = capture.get_jpeg()
                yield b"--" + boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + chunk + b"\r\n"
                time.sleep(0.04)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    if serve_static and dist_dir.is_dir():
        index = dist_dir / "index.html"

        @app.get("/{full_path:path}")
        def spa(full_path: str) -> FileResponse:
            f = dist_dir / full_path
            return FileResponse(f) if f.is_file() else FileResponse(index)

    return app
