# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import json
import struct
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from auto_fish_executor import AutoFishExecutor
from capture_service import CaptureService
from tools.exec_msg import snapshot as msg_snapshot

WS_PREVIEW_HEADER = struct.Struct('>fI')  # 实测 FPS + UTF-8 JSON meta（page_match、crop 尺寸）字节长度


class SetFpsBody(BaseModel):
    """POST `/api/capture/fps` 的请求体。"""

    fps: float = Field(ge=1, le=60)


class SetMatchThresholdBody(BaseModel):
    """POST `/api/capture/match-threshold` 的请求体。"""

    threshold: float = Field(ge=0, le=1)


def create_app(
    *,
    capture: CaptureService,
    auto_fish: AutoFishExecutor,
    serve_static: bool,
    dist_dir: Path,
) -> FastAPI:
    """组装 FastAPI：捕获相关 API，可选 SPA 静态目录。"""

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """进程生命周期内启动/停止捕获后台线程。"""
        capture.start_background()
        yield
        auto_fish.stop()
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
        """返回窗口是否就绪、HWND、裁剪后尺寸、当前 FPS、预览 MIME。"""
        s = capture.get_status()
        return {
            "ok": s.ok,
            "hwnd": s.hwnd,
            "width": s.width,
            "height": s.height,
            "fps": s.fps,
            "preview_mime": s.preview_mime,
            "page_match": s.page_match,
            "page_match_threshold": s.page_match_threshold,
            "pipeline_ms": s.pipeline_ms,
            "reeling_bar_debug": s.reeling_bar_debug,
        }

    @app.post("/api/capture/fps")
    def cap_set_fps(body: SetFpsBody) -> dict[str, float]:
        """设置捕获循环与预览推送的目标帧率（1–60）。"""
        return {"fps": capture.set_fps(body.fps)}

    @app.post("/api/capture/match-threshold")
    def cap_set_match_threshold(body: SetMatchThresholdBody) -> dict[str, float]:
        """设置页面模板匹配的相似度下限（0–1，越大越苛刻）。"""
        return {"page_match_threshold": capture.set_page_match_threshold(body.threshold)}

    @app.get("/api/auto-fish/status")
    def auto_fish_status() -> dict[str, object]:
        """自动钓鱼执行器是否在跑、最近一次识别到的 page_id。"""
        return auto_fish.status_dict()

    @app.post("/api/auto-fish/start")
    def auto_fish_start() -> dict[str, object]:
        """启动自动钓鱼轮询线程（幂等：已在跑则 `started: false`）。"""
        return auto_fish.start()

    @app.post("/api/auto-fish/stop")
    def auto_fish_stop() -> dict[str, object]:
        """停止自动钓鱼线程。"""
        return auto_fish.stop()

    @app.get("/api/msg/log")
    def msg_log() -> dict[str, Any]:
        """执行过程文本行（时间戳 + 文案），供前端终端面板轮询。"""
        return {"lines": msg_snapshot()}

    @app.websocket("/api/capture/ws")
    async def cap_ws(ws: WebSocket) -> None:
        """预览 WebSocket：首条文本 JSON `mime`；随后每条二进制为 `>f` FPS + `>I` meta 长度 + JSON + 图像字节。"""

        def pack_preview(
            pix: bytes,
            fps: float,
            page_match: dict[str, object] | None,
            crop_w: int,
            crop_h: int,
            pipeline_ms: dict[str, float],
            reeling_bar_debug: dict[str, object] | None,
        ) -> bytes:
            meta = json.dumps(
                {
                    "page_match": page_match,
                    "crop_width": crop_w,
                    "crop_height": crop_h,
                    "pipeline_ms": pipeline_ms,
                    "reeling_bar_debug": reeling_bar_debug,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            return WS_PREVIEW_HEADER.pack(fps, len(meta)) + meta + pix

        await ws.accept()
        await ws.send_json({"mime": capture.preview_mime()})
        loop = asyncio.get_running_loop()
        try:
            pix, fps, pm, cw, ch, pipe, rbd = await loop.run_in_executor(None, capture.get_preview_with_live_fps)
            await ws.send_bytes(pack_preview(pix, fps, pm, cw, ch, pipe, rbd))
            while True:
                timeout = capture.mjpeg_sleep_s()
                pix, fps, pm, cw, ch, pipe, rbd = await loop.run_in_executor(
                    None,
                    capture.wait_next_preview_with_live_fps,
                    timeout,
                )
                await ws.send_bytes(pack_preview(pix, fps, pm, cw, ch, pipe, rbd))
        except WebSocketDisconnect:
            pass

    @app.get("/api/capture/mjpeg")
    def cap_mjpeg() -> StreamingResponse:
        """multipart MJPEG 流（调试或兼容）；分片 Content-Type 与 `preview_mime` 一致。"""
        boundary = b"frame"
        ct = capture.preview_mime().encode("ascii")

        def gen():
            """首帧立即送出；之后在新帧就绪时唤醒，否则按 FPS 兜底。"""
            chunk = capture.get_preview_bytes()
            hdr = b"--" + boundary + b"\r\nContent-Type: " + ct + b"\r\n\r\n"
            while True:
                yield hdr + chunk + b"\r\n"
                chunk = capture.wait_next_frame(timeout_s=capture.mjpeg_sleep_s())

        return StreamingResponse(
            gen(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    if serve_static and dist_dir.is_dir():
        index = dist_dir / "index.html"

        @app.get("/{full_path:path}")
        def spa(full_path: str) -> FileResponse:
            """存在文件则直接返回，否则回落到 `index.html`（SPA）。"""
            f = dist_dir / full_path
            return FileResponse(f) if f.is_file() else FileResponse(index)

    return app
