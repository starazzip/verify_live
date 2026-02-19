"""verify_live API 設定。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv


VERIFY_ROOT = Path(__file__).resolve().parents[2]
PARENT_ROOT = VERIFY_ROOT.parent

ENV_FILE = VERIFY_ROOT / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

_workspace_default = PARENT_ROOT if (PARENT_ROOT / "user_data").exists() else VERIFY_ROOT
WORKSPACE_ROOT = Path(
    os.getenv("VERIFY_LIVE_WORKSPACE_ROOT", str(_workspace_default))
).resolve()


def _unique_paths(paths: Iterable[Path]) -> List[Path]:
    uniq: List[Path] = []
    for p in paths:
        rp = p.resolve()
        if rp not in uniq:
            uniq.append(rp)
    return uniq


PATH_BASES = _unique_paths([WORKSPACE_ROOT, PARENT_ROOT, VERIFY_ROOT])


def resolve_project_path(path_str: str) -> Path:
    path = Path(path_str)
    if path.is_absolute():
        return path.resolve()
    candidates = [(base / path).resolve() for base in PATH_BASES]
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0]


def _extract_userdir(path: Path) -> Optional[Path]:
    parts = path.resolve().parts
    for idx, part in enumerate(parts):
        if part.lower() == "user_data":
            return Path(*parts[: idx + 1]).resolve()
    return None


def resolve_userdir(hints: Iterable[str]) -> Optional[Path]:
    for hint in hints:
        item = str(hint).strip()
        if not item:
            continue
        userdir = _extract_userdir(resolve_project_path(item))
        if userdir is not None and userdir.exists():
            return userdir

    for base in PATH_BASES:
        cand = (base / "user_data").resolve()
        if cand.exists():
            return cand
    return None

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
        paths.append(resolve_project_path(item))
    return paths


DEFAULT_USERDIR = resolve_userdir([])
if DEFAULT_USERDIR is None:
    DEFAULT_USERDIR = (WORKSPACE_ROOT / "user_data").resolve()

DEFAULT_CONFIG_ROOTS = [
    DEFAULT_USERDIR / "configs",
    DEFAULT_USERDIR / "bot_spot_zz_hkrsif_freq" / "configs",
]
CONFIG_ROOTS = _parse_roots(os.getenv("VERIFY_LIVE_CONFIG_ROOTS", "")) or DEFAULT_CONFIG_ROOTS

API_HOST = os.getenv("VERIFY_LIVE_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("VERIFY_LIVE_API_PORT", "8011"))
WEB_PORT = int(os.getenv("VERIFY_LIVE_WEB_PORT", "5179"))

_venv_freqtrade_windows = WORKSPACE_ROOT / ".venv" / "Scripts" / "freqtrade.exe"
_venv_freqtrade_linux = WORKSPACE_ROOT / ".venv" / "bin" / "freqtrade"
if _venv_freqtrade_windows.exists():
    DEFAULT_FREQTRADE_BIN = str(_venv_freqtrade_windows)
elif _venv_freqtrade_linux.exists():
    DEFAULT_FREQTRADE_BIN = str(_venv_freqtrade_linux)
else:
    DEFAULT_FREQTRADE_BIN = "freqtrade"
FREQTRADE_BIN = os.getenv("VERIFY_LIVE_FREQTRADE_BIN", DEFAULT_FREQTRADE_BIN)

DEFAULT_PRICE_TOL_BPS = float(os.getenv("VERIFY_LIVE_DEFAULT_PRICE_TOL_BPS", "10"))
DEFAULT_QTY_TOL_RATIO = float(os.getenv("VERIFY_LIVE_DEFAULT_QTY_TOL_RATIO", "0.005"))
DOWNLOAD_EXTRA_TIMEFRAMES = os.getenv("VERIFY_LIVE_DOWNLOAD_EXTRA_TIMEFRAMES", "4h,1d")

REQUEST_TIMEOUT_SEC = int(os.getenv("VERIFY_LIVE_HTTP_TIMEOUT_SEC", "20"))
