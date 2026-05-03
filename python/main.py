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


def root() -> Path:
    """仓库根目录。"""
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
        print(
            f"缺少 {d}\ncd frontend && pnpm i && pnpm build\n或 python python/main.py --dev",
            file=sys.stderr,
        )
        sys.exit(1)

    cap = CaptureService()
    fish = AutoFishExecutor(cap)
    app = create_app(capture=cap, auto_fish=fish, serve_static=static, dist_dir=d)

    srv = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="info", access_log=False))
    threading.Thread(target=srv.run, daemon=True).start()
    time.sleep(0.35)

    url = args.url if args.dev else f"http://{args.host}:{args.port}"
    webview.create_window("异环钓鱼", url, width=960, height=720, min_size=(480, 520), resizable=True)

    try:
        webview.start()
    except KeyboardInterrupt:
        srv.should_exit = True


if __name__ == "__main__":
    main()
