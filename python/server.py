# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import json
import logging
import struct
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from features.auto_fish.auto_fish_executor import AutoFishExecutor
from capture_service import CaptureService
from features.manager.manager_executor import ManagerExecutor
from features.music.music_executor import MusicExecutor
from features.piano.piano_executor import PianoExecutor
from tools.exec_msg import snapshot as msg_snapshot, start_admin_warn_loop, stop_admin_warn_loop
import tools.game_input as game_input
from tools.app_settings import AppSettingsPayload, HotkeyPayload, load_app_settings, save_app_settings

_log = logging.getLogger(__name__)

WS_PREVIEW_HEADER = struct.Struct('>fI')  # 实测 FPS + UTF-8 JSON meta（page_match、crop 尺寸）字节长度


class SetFpsBody(BaseModel):
    """POST `/api/capture/fps` 的请求体。"""

    fps: float = Field(ge=1, le=60)


class SetMatchThresholdBody(BaseModel):
    """POST `/api/capture/match-threshold` 的请求体。"""

    threshold: float = Field(ge=0, le=1)


class SetCaptureContextBody(BaseModel):
    """POST `/api/capture/context`：切换页面匹配使用的配置（钓鱼 / music / piano / manager 各用各自 JSON）。"""

    context: Literal["fish", "music", "piano", "manager"]


class SetAutoFishLogicBody(BaseModel):
    """POST `/api/auto-fish/logic`：手动切换自动执行逻辑状态。"""

    logic_state: Literal["fishing", "sell-fish", "bait"]


class SetAutoFishSellOnNoBaitBody(BaseModel):
    """POST `/api/auto-fish/sell-on-no-bait`：无鱼饵时是否走卖鱼流程（关则直接鱼饵）。"""

    enabled: bool


class SetManagerDirectKnockBody(BaseModel):
    """POST `/api/manager/direct-knock`：店长特供页是否仅固定坐标连点（关则图像采集后再决策）。"""

    enabled: bool


class SetManagerAutoSelectLevelBody(BaseModel):
    """POST `/api/manager/auto-select-level`：选关页是否自动点击最新关卡。"""

    enabled: bool


class PianoSelectScoreBody(BaseModel):
    """POST `/api/piano/scores/select`：选中曲谱（`scores/*.json` 的文件名 stem）。"""

    id: str = Field(min_length=1)


class PianoCreateScoreBody(BaseModel):
    """POST `/api/piano/scores`：新建曲谱。"""

    mode: Literal["friendly", "raw"] = "friendly"
    title: str | None = None
    beat_seconds: float | None = Field(None, ge=0.05, le=120.0)
    beatSeconds: float | None = Field(None, ge=0.05, le=120.0)
    notes: list[dict[str, Any]] | None = None
    raw_json: str | None = None


class PianoUpdateScoreBody(PianoCreateScoreBody):
    """PUT `/api/piano/scores/{score_id}`：更新已有曲谱。"""


PY_DIR = Path(__file__).resolve().parent


def create_app(
    *,
    capture: CaptureService,
    auto_fish: AutoFishExecutor,
    music: MusicExecutor,
    piano: PianoExecutor,
    manager: ManagerExecutor,
    serve_static: bool,
    dist_dir: Path,
) -> FastAPI:
    """组装 FastAPI：捕获相关 API，可选 SPA 静态目录。"""

    app_settings_lock = threading.Lock()
    app_settings_state: AppSettingsPayload = load_app_settings(base_dir=PY_DIR)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """进程生命周期内启动/停止捕获后台线程。"""
        capture.start_background()
        start_admin_warn_loop()

        def _click_offsets() -> tuple[int, int]:
            with app_settings_lock:
                s = app_settings_state
                return (int(s.click_offset_x), int(s.click_offset_y))

        game_input.set_click_offset_provider(_click_offsets)

        hotkey_done = threading.Event()

        def _hotkey_listener() -> None:
            from pynput import keyboard

            def _norm_key(k: object) -> str | None:
                if isinstance(k, keyboard.KeyCode):
                    if k.char is None:
                        return None
                    ch = k.char
                    if ch == " ":
                        return "Space"
                    if len(ch) == 1:
                        return ch.upper()
                    return ch
                if isinstance(k, keyboard.Key):
                    name = k.name
                    if name is None:
                        return None
                    # 兼容 function keys: 'f12' -> 'F12'
                    if name.startswith("f") and name[1:].isdigit():
                        return name.upper()
                    # 常见键名首字母大写
                    if name == "space":
                        return "Space"
                    return name[0].upper() + name[1:]
                return None

            def _is_modifier(k: object) -> bool:
                return k in (
                    keyboard.Key.ctrl,
                    keyboard.Key.ctrl_l,
                    keyboard.Key.ctrl_r,
                    keyboard.Key.shift,
                    keyboard.Key.shift_l,
                    keyboard.Key.shift_r,
                    keyboard.Key.alt,
                    keyboard.Key.alt_l,
                    keyboard.Key.alt_r,
                    keyboard.Key.cmd,
                    keyboard.Key.cmd_l,
                    keyboard.Key.cmd_r,
                )

            pressed_mods: set[str] = set()

            def _mods_snapshot() -> dict[str, bool]:
                return {
                    "ctrl": ("ctrl" in pressed_mods),
                    "shift": ("shift" in pressed_mods),
                    "alt": ("alt" in pressed_mods),
                    "meta": ("meta" in pressed_mods),
                }

            def on_press(k: object) -> None:
                # 更新修饰键状态
                if k in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    pressed_mods.add("ctrl")
                    return
                if k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    pressed_mods.add("shift")
                    return
                if k in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    pressed_mods.add("alt")
                    return
                if k in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
                    pressed_mods.add("meta")
                    return

                key = _norm_key(k)
                if key is None:
                    return

                with app_settings_lock:
                    hk = app_settings_state

                mods = _mods_snapshot()

                def _match(target: HotkeyPayload) -> bool:
                    if target.key is None or target.key == "":
                        return False
                    if target.key != key:
                        return False
                    return (
                        bool(target.ctrl) == bool(mods["ctrl"])
                        and bool(target.shift) == bool(mods["shift"])
                        and bool(target.alt) == bool(mods["alt"])
                        and bool(target.meta) == bool(mods["meta"])
                    )

                if _match(hk.stop):
                    auto_fish.stop()
                    music.stop()
                    piano.stop()
                    manager.stop()
                    return

                if _match(hk.start):
                    # 根据当前模式启动对应执行器（与前端切换的 context 一致）
                    try:
                        ctx = capture.get_status().capture_context
                        if ctx == "music":
                            auto_fish.stop()
                            piano.stop()
                            manager.stop()
                            music.start()
                        elif ctx == "piano":
                            auto_fish.stop()
                            music.stop()
                            manager.stop()
                            piano.start()
                        elif ctx == "manager":
                            auto_fish.stop()
                            music.stop()
                            piano.stop()
                            manager.start()
                        else:
                            music.stop()
                            piano.stop()
                            manager.stop()
                            auto_fish.start()
                    except Exception:
                        # 启动失败不影响监听线程
                        return

            def on_release(k: object) -> None:
                if k in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    pressed_mods.discard("ctrl")
                    return
                if k in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                    pressed_mods.discard("shift")
                    return
                if k in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    pressed_mods.discard("alt")
                    return
                if k in (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r):
                    pressed_mods.discard("meta")
                    return

            with keyboard.Listener(on_press=on_press, on_release=on_release):
                hotkey_done.wait()

        hotkey_t = threading.Thread(target=_hotkey_listener, name="global-hotkeys", daemon=True)
        hotkey_t.start()
        yield
        stop_admin_warn_loop()
        hotkey_done.set()
        hotkey_t.join(timeout=2.0)
        auto_fish.stop()
        music.stop()
        piano.stop()
        manager.stop()
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

    @app.get("/api/settings")
    def get_app_settings() -> dict[str, Any]:
        """读取应用设置（快捷键、点击校准等，持久化到 python/app-settings.json）。"""
        with app_settings_lock:
            return app_settings_state.model_dump()

    @app.post("/api/settings")
    def set_app_settings(body: AppSettingsPayload) -> dict[str, Any]:
        """更新应用设置并持久化。"""
        nonlocal app_settings_state
        with app_settings_lock:
            app_settings_state = body
            save_app_settings(base_dir=PY_DIR, settings=app_settings_state)
            return app_settings_state.model_dump()

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
            "capture_context": s.capture_context,
            "page_match": s.page_match,
            "page_match_threshold": s.page_match_threshold,
            "pipeline_ms": s.pipeline_ms,
            "reeling_bar_debug": s.reeling_bar_debug,
            "music_drum_debug": s.music_drum_debug,
        }

    @app.post("/api/capture/fps")
    def cap_set_fps(body: SetFpsBody) -> dict[str, float]:
        """设置捕获循环与预览推送的目标帧率（1–60）。"""
        return {"fps": capture.set_fps(body.fps)}

    @app.post("/api/capture/match-threshold")
    def cap_set_match_threshold(body: SetMatchThresholdBody) -> dict[str, float]:
        """设置页面模板匹配的相似度下限（0–1，越大越苛刻）。"""
        return {"page_match_threshold": capture.set_page_match_threshold(body.threshold)}

    @app.post("/api/capture/context")
    def cap_set_context(body: SetCaptureContextBody) -> dict[str, float | str]:
        """切换捕获管线使用的页面 JSON（钓鱼 / 超强音 / 钢琴 / 店长），并重置匹配阈值为该模式默认值。"""
        ctx = capture.set_capture_context(body.context)
        return {"capture_context": ctx, "page_match_threshold": capture.get_page_match_threshold()}

    @app.get("/api/auto-fish/status")
    def auto_fish_status() -> dict[str, object]:
        """自动钓鱼执行器是否在跑、最近一次识别到的 page_id。"""
        return auto_fish.status_dict()

    @app.post("/api/auto-fish/start")
    def auto_fish_start() -> dict[str, object]:
        """启动自动钓鱼轮询线程（幂等：已在跑则 `started: false`）。"""
        music.stop()
        piano.stop()
        return auto_fish.start()

    @app.post("/api/auto-fish/stop")
    def auto_fish_stop() -> dict[str, object]:
        """停止自动钓鱼线程。"""
        return auto_fish.stop()

    @app.post("/api/auto-fish/logic")
    def auto_fish_set_logic(body: SetAutoFishLogicBody) -> dict[str, object]:
        """切换钓鱼 / 卖鱼 / 鱼饵逻辑（与执行器 `logic_state` 一致）。"""
        return auto_fish.set_logic_state(body.logic_state)

    @app.post("/api/auto-fish/sell-on-no-bait")
    def auto_fish_set_sell_on_no_bait(body: SetAutoFishSellOnNoBaitBody) -> dict[str, object]:
        """无鱼饵时是否进入卖鱼逻辑；关闭则进入鱼饵逻辑。"""
        return auto_fish.set_sell_fish_on_no_bait(body.enabled)

    @app.get("/api/music/status")
    def music_status() -> dict[str, object]:
        """超强音执行器是否在跑、当前生效规则数、上次触发的 rule_id。"""
        return music.status_dict()

    @app.post("/api/music/start")
    def music_start() -> dict[str, object]:
        """启动超强音 ROI 匹配线程；会先停止自动钓鱼。"""
        auto_fish.stop()
        piano.stop()
        manager.stop()
        return music.start()

    @app.post("/api/music/stop")
    def music_stop() -> dict[str, object]:
        """停止超强音线程。"""
        return music.stop()

    @app.get("/api/piano/status")
    def piano_status() -> dict[str, object]:
        """钢琴执行器是否在跑、最近一次识别到的 page_id。"""
        return piano.status_dict()

    @app.get("/api/piano/scores")
    def piano_scores_list() -> dict[str, Any]:
        """列出 `features/piano/scores` 下曲谱（按 ``updateAt`` 降序），并附带当前选中 id。"""
        return {"scores": piano.list_score_summaries(), "selected_id": piano.status_dict().get("score_id")}

    @app.get("/api/piano/scores/{score_id}")
    def piano_scores_get(score_id: str) -> dict[str, Any]:
        """读取单个曲谱完整 JSON，供编辑弹窗回填。"""
        try:
            return piano.get_score(score_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="score not found") from None

    @app.post("/api/piano/scores/select")
    def piano_scores_select(body: PianoSelectScoreBody) -> dict[str, Any]:
        """切换选中曲谱并重置播放进度。"""
        try:
            return piano.set_selected_score(body.id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="score not found") from None

    @app.post("/api/piano/scores")
    def piano_scores_create(body: PianoCreateScoreBody) -> dict[str, Any]:
        """新建曲谱 JSON（文件名随机 hex）；校验 ``notes`` 与 ``pitch``。"""
        try:
            if body.mode == "raw":
                if body.raw_json is None or not str(body.raw_json).strip():
                    raise HTTPException(status_code=400, detail="raw_json required")
                raw = json.loads(body.raw_json)
                if not isinstance(raw, dict):
                    raise HTTPException(status_code=400, detail="raw_json must be an object")
                return piano.create_score_from_raw_dict(raw)
            bs = body.beat_seconds if body.beat_seconds is not None else body.beatSeconds
            if bs is None:
                bs = 1.0
            title = (body.title or "").strip() or "未命名"
            notes = body.notes if body.notes is not None else []
            return piano.create_score(title, float(bs), list(notes))
        except HTTPException:
            raise
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.put("/api/piano/scores/{score_id}")
    def piano_scores_update(score_id: str, body: PianoUpdateScoreBody) -> dict[str, Any]:
        """更新已有曲谱 JSON，并刷新 ``updateAt``。"""
        try:
            if body.mode == "raw":
                if body.raw_json is None or not str(body.raw_json).strip():
                    raise HTTPException(status_code=400, detail="raw_json required")
                raw = json.loads(body.raw_json)
                if not isinstance(raw, dict):
                    raise HTTPException(status_code=400, detail="raw_json must be an object")
                return piano.update_score_from_raw_dict(score_id, raw)
            bs = body.beat_seconds if body.beat_seconds is not None else body.beatSeconds
            if bs is None:
                bs = 1.0
            title = (body.title or "").strip() or "未命名"
            notes = body.notes if body.notes is not None else []
            return piano.update_score(score_id, title, float(bs), list(notes))
        except HTTPException:
            raise
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="score not found") from None
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"invalid json: {e}") from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.delete("/api/piano/scores/{score_id}")
    def piano_scores_delete(score_id: str) -> dict[str, Any]:
        """删除已有曲谱；若删除的是当前选中曲谱，则自动切到剩余最新曲谱。"""
        try:
            return piano.delete_score(score_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="score not found") from None

    @app.post("/api/piano/start")
    def piano_start() -> dict[str, object]:
        """启动钢琴线程；会先停止自动钓鱼与其它模式执行器。"""
        auto_fish.stop()
        music.stop()
        manager.stop()
        return piano.start()

    @app.post("/api/piano/stop")
    def piano_stop() -> dict[str, object]:
        """停止钢琴线程。"""
        return piano.stop()

    @app.get("/api/manager/status")
    def manager_status() -> dict[str, object]:
        """店长特供执行器是否在跑、最近一次识别到的 page_id。"""
        return manager.status_dict()

    @app.post("/api/manager/start")
    def manager_start() -> dict[str, object]:
        """启动店长特供线程；会先停止其他执行器。"""
        auto_fish.stop()
        music.stop()
        piano.stop()
        return manager.start()

    @app.post("/api/manager/stop")
    def manager_stop() -> dict[str, object]:
        """停止店长特供线程。"""
        return manager.stop()

    @app.post("/api/manager/direct-knock")
    def manager_set_direct_knock(body: SetManagerDirectKnockBody) -> dict[str, object]:
        """店长特供页跳过多匹配与槽位采集，仅对固定坐标节流点击。"""
        return manager.set_direct_knock(body.enabled)

    @app.post("/api/manager/auto-select-level")
    def manager_set_auto_select_level(body: SetManagerAutoSelectLevelBody) -> dict[str, object]:
        """选关页是否自动点击最新关卡。"""
        return manager.set_auto_select_level(body.enabled)

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
            music_drum_debug: dict[str, object] | None,
        ) -> bytes:
            meta = json.dumps(
                {
                    "page_match": page_match,
                    "crop_width": crop_w,
                    "crop_height": crop_h,
                    "pipeline_ms": pipeline_ms,
                    "reeling_bar_debug": reeling_bar_debug,
                    "music_drum_debug": music_drum_debug,
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
            mdd = await loop.run_in_executor(None, capture.get_music_drum_debug)
            await ws.send_bytes(pack_preview(pix, fps, pm, cw, ch, pipe, rbd, mdd))
            while True:
                timeout = capture.mjpeg_sleep_s()
                pix, fps, pm, cw, ch, pipe, rbd = await loop.run_in_executor(
                    None,
                    capture.wait_next_preview_with_live_fps,
                    timeout,
                )
                mdd = await loop.run_in_executor(None, capture.get_music_drum_debug)
                await ws.send_bytes(pack_preview(pix, fps, pm, cw, ch, pipe, rbd, mdd))
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
