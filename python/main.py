# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

from auto_fish_executor import AutoFishExecutor
from capture_service import CaptureService
from server import create_app


class WindowChromeApi:
    """无框窗口顶栏：JS 调最小化 / 关闭。"""

    def minimize_window(self) -> None:
        for w in webview.windows:
            w.minimize()
            return

    def close_window(self) -> None:
        for w in webview.windows:
            w.destroy()
            return


def root() -> Path:
    """仓库根目录；冻结构建下为 exe 所在目录（与 `frontend/dist` 同级）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def dist() -> Path:
    """前端构建产物目录（Vite `pnpm build` 输出）。"""
    return root() / "frontend" / "dist"


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。"""
    p = argparse.ArgumentParser(description="yh-fish")
    p.add_argument("--dev", action="store_true", help="加载 Vite（需另开 pnpm dev）")
    p.add_argument("--url", default="http://localhost:5173", help="--dev 时地址")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8848)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """后台启动 FastAPI，再打开桌面 WebView 加载前端。"""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    d = dist()
    static = not args.dev

    if static and not d.is_dir():
        msg = f"缺少前端资源目录：\n{d}\n\n请重新安装，或使用开发模式：\npython python/main.py --dev"
        if getattr(sys, "frozen", False):
            try:
                import ctypes

                ctypes.windll.user32.MessageBoxW(0, msg, "异环钓鱼工具", 0x10)
            except Exception:
                pass
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)

    cap = CaptureService()
    fish = AutoFishExecutor(cap)
    app = create_app(capture=cap, auto_fish=fish, serve_static=static, dist_dir=d)

    srv = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="info", access_log=False))
    threading.Thread(target=srv.run, daemon=True).start()
    time.sleep(0.35)

    url = args.url if args.dev else f"http://{args.host}:{args.port}"
    webview.create_window(
        "异环钓鱼工具",
        url,
        width=960,
        height=700,
        min_size=(480, 520),
        resizable=True,
        frameless=True,
        easy_drag=False,
        js_api=WindowChromeApi(),
    )

    try:
        webview.start()
    except KeyboardInterrupt:
        srv.should_exit = True


if __name__ == "__main__":
    main()
