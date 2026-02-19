#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""跨平台啟動 verify_live Web。"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def npm_bin() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def main() -> None:
    parser = argparse.ArgumentParser(description="start verify_live web")
    parser.add_argument("--api-base", default="http://127.0.0.1:8011")
    parser.add_argument("--port", type=int, default=5179)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    web_dir = root / "verify_live_web"
    env = os.environ.copy()
    env["VITE_VERIFY_LIVE_API_BASE"] = str(args.api_base)
    cmd = [npm_bin(), "run", "dev", "--", "--host", "127.0.0.1", "--port", str(args.port)]
    raise SystemExit(subprocess.call(cmd, cwd=web_dir, env=env))


if __name__ == "__main__":
    main()

