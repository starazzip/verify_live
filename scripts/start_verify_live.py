#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨平台一鍵啟動 verify_live API + Web。"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional

from _env_loader import env_int, env_str, load_dotenv


def pick_api_python(api_dir: Path) -> str:
    candidates = [
        api_dir / ".venv" / "Scripts" / "python.exe",  # Windows
        api_dir / ".venv" / "bin" / "python",  # Linux/macOS
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return sys.executable


def npm_bin() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def terminate_process(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=8)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root)

    default_api_host = env_str("VERIFY_LIVE_API_HOST", "127.0.0.1")
    default_api_port = env_int("VERIFY_LIVE_API_PORT", 8011)
    default_web_port = env_int("VERIFY_LIVE_WEB_PORT", 5179)

    parser = argparse.ArgumentParser(description="start verify_live api + web")
    parser.add_argument("--api-host", default=default_api_host)
    parser.add_argument("--api-port", type=int, default=default_api_port)
    parser.add_argument("--web-port", type=int, default=default_web_port)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    api_dir = root / "verify_live_api"
    web_dir = root / "verify_live_web"

    api_python = pick_api_python(api_dir)
    api_cmd = [
        api_python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        str(args.api_host),
        "--port",
        str(args.api_port),
    ]

    web_cmd = [npm_bin(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.web_port)]
    web_env = os.environ.copy()
    web_env["VITE_VERIFY_LIVE_API_BASE"] = f"http://{args.api_host}:{args.api_port}"

    print(f"[verify_live] API 啟動：{' '.join(api_cmd)}")
    api_proc = subprocess.Popen(api_cmd, cwd=api_dir)
    print(f"[verify_live] WEB 啟動：{' '.join(web_cmd)}")
    web_proc = subprocess.Popen(web_cmd, cwd=web_dir, env=web_env)

    if not args.no_browser:
        time.sleep(2)
        webbrowser.open(f"http://127.0.0.1:{args.web_port}")

    print("[verify_live] 已啟動，按 Ctrl+C 停止。")
    try:
        while True:
            time.sleep(1)
            api_rc = api_proc.poll()
            web_rc = web_proc.poll()
            if api_rc is not None:
                raise RuntimeError(f"API 已結束，exit_code={api_rc}")
            if web_rc is not None:
                raise RuntimeError(f"WEB 已結束，exit_code={web_rc}")
    except KeyboardInterrupt:
        print("\n[verify_live] 收到 Ctrl+C，停止中...")
    except Exception as exc:
        print(f"[verify_live] 發生錯誤：{exc}")
    finally:
        terminate_process(web_proc)
        terminate_process(api_proc)
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(api_proc.pid), signal.SIGTERM)  # type: ignore[arg-type]
            except Exception:
                pass
        print("[verify_live] 已停止。")


if __name__ == "__main__":
    main()
