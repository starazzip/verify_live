#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨平台啟動 verify_live API。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root)

    default_host = env_str("VERIFY_LIVE_API_HOST", "127.0.0.1")
    default_port = env_int("VERIFY_LIVE_API_PORT", 8011)

    parser = argparse.ArgumentParser(description="start verify_live api")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()

    api_dir = root / "verify_live_api"
    api_python = pick_api_python(api_dir)
    cmd = [
        api_python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        str(args.host),
        "--port",
        str(args.port),
    ]
    raise SystemExit(subprocess.call(cmd, cwd=api_dir))


if __name__ == "__main__":
    main()
