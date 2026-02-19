#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""啟動腳本用的簡易 .env 讀取工具。"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(root: Path) -> None:
    """讀取 root/.env，僅填入目前未設定的環境變數。"""
    env_file = root / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return str(value)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(str(value).strip())
    except Exception:
        return default

