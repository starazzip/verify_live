#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨平台一鍵啟動 verify_live API + Web。"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


def spawn_process(
    cmd: list[str],
    *,
    cwd: Path,
    env: Optional[dict[str, str]] = None,
) -> subprocess.Popen:
    kwargs: dict = {"cwd": cwd}
    if env is not None:
        kwargs["env"] = env
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["preexec_fn"] = os.setsid
    return subprocess.Popen(cmd, **kwargs)


def terminate_process(proc: Optional[subprocess.Popen]) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        # Windows 下優先送 CTRL_BREAK_EVENT，再用 taskkill /T 清整棵程序樹。
        try:
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
            return
        except Exception:
            pass
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        return

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=6)
        return
    except Exception:
        pass
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def is_verify_api_alive(host: str, port: int) -> bool:
    url = f"http://{host}:{port}/api/verify/health"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return bool(payload.get("ok"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return False


def pids_listening_on(host: str, port: int) -> list[int]:
    # 目前以 IPv4 127.0.0.1 為主；若後續要支援更多情境可再擴充。
    pids: set[int] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex((host, port)) != 0:
                return []
    except Exception:
        return []

    # 跨平台最穩定做法：呼叫 netstat 再解析 PID
    if os.name == "nt":
        cmd = ["netstat", "-ano", "-p", "tcp"]
    else:
        cmd = ["netstat", "-anp", "tcp"]
    try:
        out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="ignore")
    except Exception:
        return []

    needle = f"{host}:{port}"
    for line in out.splitlines():
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        pid_raw = parts[-1]
        try:
            pid = int(pid_raw)
            pids.add(pid)
        except Exception:
            continue
    return sorted(pids)


def force_kill_pid_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        time.sleep(0.3)
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
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
    parser.add_argument(
        "--restart-api",
        action="store_true",
        help="若 API 埠已被占用，先強制關閉占用程序再啟動新 API。",
    )
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

    api_proc: Optional[subprocess.Popen] = None
    if is_port_in_use(args.api_host, args.api_port):
        if args.restart_api:
            pids = pids_listening_on(args.api_host, args.api_port)
            if not pids:
                raise RuntimeError(
                    f"連接埠 {args.api_host}:{args.api_port} 被占用，但無法取得 PID。"
                )
            print(
                f"[verify_live] --restart-api 啟用，關閉占用 {args.api_host}:{args.api_port} 的 PID: {pids}"
            )
            for pid in pids:
                force_kill_pid_tree(pid)
            time.sleep(1)
            if is_port_in_use(args.api_host, args.api_port):
                raise RuntimeError(
                    f"已嘗試重啟 API，但連接埠 {args.api_host}:{args.api_port} 仍被占用。"
                )
            print(f"[verify_live] API 啟動：{' '.join(api_cmd)}")
            api_proc = spawn_process(api_cmd, cwd=api_dir)
        elif is_verify_api_alive(args.api_host, args.api_port):
            print(
                f"[verify_live] 偵測到既有 verify_live API："
                f"http://{args.api_host}:{args.api_port}，沿用既有服務。"
            )
        else:
            raise RuntimeError(
                f"連接埠 {args.api_host}:{args.api_port} 已被占用，且非 verify_live API。"
                "請更換埠號或關閉占用程序。"
            )
    else:
        print(f"[verify_live] API 啟動：{' '.join(api_cmd)}")
        api_proc = spawn_process(api_cmd, cwd=api_dir)

    print(f"[verify_live] WEB 啟動：{' '.join(web_cmd)}")
    web_proc = spawn_process(web_cmd, cwd=web_dir, env=web_env)

    if not args.no_browser:
        time.sleep(2)
        webbrowser.open(f"http://127.0.0.1:{args.web_port}")

    print("[verify_live] 已啟動，按 Ctrl+C 停止。")
    try:
        while True:
            time.sleep(1)
            api_rc = api_proc.poll() if api_proc is not None else None
            web_rc = web_proc.poll()
            if api_proc is not None and api_rc is not None:
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
        print("[verify_live] 已停止。")


if __name__ == "__main__":
    main()
