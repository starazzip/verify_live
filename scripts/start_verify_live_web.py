#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨平台啟動 verify_live Web。"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from _env_loader import env_int, env_str, load_dotenv


def npm_bin() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root)

    default_api_host = env_str("VERIFY_LIVE_API_HOST", "127.0.0.1")
    default_api_port = env_int("VERIFY_LIVE_API_PORT", 8011)
    default_web_port = env_int("VERIFY_LIVE_WEB_PORT", 5179)
    default_api_base = f"http://{default_api_host}:{default_api_port}"

    parser = argparse.ArgumentParser(description="start verify_live web")
    parser.add_argument("--api-base", default=default_api_base)
    parser.add_argument("--port", type=int, default=default_web_port)
    args = parser.parse_args()

    web_dir = root / "verify_live_web"
    env = os.environ.copy()
    env["VITE_VERIFY_LIVE_API_BASE"] = str(args.api_base)
    cmd = [npm_bin(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.port)]
    raise SystemExit(subprocess.call(cmd, cwd=web_dir, env=env))


if __name__ == "__main__":
    main()
