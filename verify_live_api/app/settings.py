"""verify_live API 設定。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv


VERIFY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = Path(
    os.getenv("VERIFY_LIVE_WORKSPACE_ROOT", str(VERIFY_ROOT))
).resolve()

ENV_FILE = VERIFY_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

DATA_DIR = VERIFY_ROOT / "data"
LOG_DIR = VERIFY_ROOT / "logs"
RUNS_DIR = VERIFY_ROOT / "runs"
PROFILES_DIR = VERIFY_ROOT / "profiles"
DB_PATH = DATA_DIR / "verify_live.db"

for p in [DATA_DIR, LOG_DIR, RUNS_DIR, PROFILES_DIR]:
    p.mkdir(parents=True, exist_ok=True)


def _parse_roots(raw: str) -> List[Path]:
    paths: List[Path] = []
    for token in raw.replace(";", ",").split(","):
        item = token.strip()
        if not item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = WORKSPACE_ROOT / path
        paths.append(path.resolve())
    return paths


DEFAULT_CONFIG_ROOTS = [
    WORKSPACE_ROOT / "user_data" / "configs",
    WORKSPACE_ROOT / "user_data" / "bot_spot_zz_hkrsif_freq" / "configs",
]
CONFIG_ROOTS = _parse_roots(os.getenv("VERIFY_LIVE_CONFIG_ROOTS", "")) or DEFAULT_CONFIG_ROOTS

API_HOST = os.getenv("VERIFY_LIVE_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("VERIFY_LIVE_API_PORT", "8011"))
WEB_PORT = int(os.getenv("VERIFY_LIVE_WEB_PORT", "5179"))

_venv_freqtrade = WORKSPACE_ROOT / ".venv" / "Scripts" / "freqtrade.exe"
if _venv_freqtrade.exists():
    DEFAULT_FREQTRADE_BIN = str(_venv_freqtrade)
else:
    DEFAULT_FREQTRADE_BIN = "freqtrade"
FREQTRADE_BIN = os.getenv("VERIFY_LIVE_FREQTRADE_BIN", DEFAULT_FREQTRADE_BIN)

DEFAULT_PRICE_TOL_BPS = float(os.getenv("VERIFY_LIVE_DEFAULT_PRICE_TOL_BPS", "10"))
DEFAULT_QTY_TOL_RATIO = float(os.getenv("VERIFY_LIVE_DEFAULT_QTY_TOL_RATIO", "0.005"))

REQUEST_TIMEOUT_SEC = int(os.getenv("VERIFY_LIVE_HTTP_TIMEOUT_SEC", "20"))
