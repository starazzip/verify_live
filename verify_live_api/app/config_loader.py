"""Config 掃描與解析。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List

from jinja2 import BaseLoader, Environment

from . import settings


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value


def _render_json_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() != ".j2":
        return text
    jenv = Environment(loader=BaseLoader(), autoescape=False)
    jenv.globals["env"] = _env
    return jenv.from_string(text).render()


def load_config_dict(path: Path) -> Dict:
    rendered = _render_json_text(path)
    return json.loads(rendered)


def config_to_item(path: Path) -> Dict:
    item = {
        "config_id": hashlib.md5(str(path).encode("utf-8")).hexdigest()[:16],
        "config_path": str(path),
        "label": str(path.relative_to(settings.WORKSPACE_ROOT)) if path.is_relative_to(settings.WORKSPACE_ROOT) else str(path),
        "strategy": "",
        "strategy_path": "",
        "timeframe": "5m",
        "fee": None,
        "datadir": "",
    }
    try:
        cfg = load_config_dict(path)
    except Exception:
        return item

    item["strategy"] = str(cfg.get("strategy") or "")
    item["strategy_path"] = str(cfg.get("strategy_path") or "user_data/strategies")
    item["timeframe"] = str(cfg.get("timeframe") or "5m")
    fee_val = cfg.get("fee")
    if fee_val is not None:
        try:
            item["fee"] = float(fee_val)
        except Exception:
            item["fee"] = None
    item["datadir"] = str(cfg.get("datadir") or "")
    return item


def scan_configs() -> List[Dict]:
    files: List[Path] = []
    for root in settings.CONFIG_ROOTS:
        if not root.exists():
            continue
        files.extend(root.rglob("config*.json"))
        files.extend(root.rglob("config*.j2"))
    uniq = sorted({p.resolve() for p in files if p.is_file()})
    return [config_to_item(p) for p in uniq]

