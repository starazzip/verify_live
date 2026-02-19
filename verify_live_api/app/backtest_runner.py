"""回測執行與匯出解析。"""

from __future__ import annotations

import json
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import settings


@dataclass
class BacktestResult:
    exit_code: int
    command: List[str]
    log_path: Path
    output_json: Path
    output_zip: Optional[Path]
    trades: List[Dict[str, Any]]

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def _to_json_obj(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _strategy_trades_from_obj(obj: Any, strategy_name: str) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []

    if isinstance(obj.get("trades"), list):
        return obj["trades"]
    if isinstance(obj.get("results"), list):
        return obj["results"]

    strategy_block = obj.get("strategy")
    if isinstance(strategy_block, dict):
        if strategy_name in strategy_block and isinstance(strategy_block[strategy_name], dict):
            trades = strategy_block[strategy_name].get("trades")
            if isinstance(trades, list):
                return trades
        for value in strategy_block.values():
            if isinstance(value, dict) and isinstance(value.get("trades"), list):
                return value["trades"]
    return []


def _load_from_zip(path: Path, strategy_name: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = [name for name in zf.namelist() if name.lower().endswith(".json") and "_config" not in name.lower()]
            for name in names:
                try:
                    obj = json.loads(zf.read(name).decode("utf-8"))
                except Exception:
                    continue
                trades = _strategy_trades_from_obj(obj, strategy_name)
                if trades:
                    return trades
    except Exception:
        return []
    return []


def _find_latest_zip(run_dir: Path) -> Optional[Path]:
    zips = sorted(run_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0] if zips else None


def run_backtest(
    *,
    config_path: str,
    strategy: str,
    strategy_path: str,
    timeframe: str,
    timerange: str,
    datadir: str,
    fee: Optional[float],
    run_dir: Path,
    extra_args: Optional[List[str]] = None,
) -> BacktestResult:
    run_dir.mkdir(parents=True, exist_ok=True)
    output_json = run_dir / "backtest_export.json"
    log_path = run_dir / "backtest.log"

    cmd = [
        settings.FREQTRADE_BIN,
        "backtesting",
        "--config",
        config_path,
        "--strategy",
        strategy,
        "--strategy-path",
        strategy_path,
        "--timeframe",
        timeframe,
        "--timerange",
        timerange,
        "--cache",
        "none",
        "--export",
        "trades",
        "--export-filename",
        str(output_json),
    ]
    if datadir:
        cmd += ["--datadir", datadir]
    if fee is not None:
        cmd += ["--fee", str(fee)]
    if extra_args:
        cmd += extra_args

    proc = subprocess.run(
        cmd,
        cwd=settings.WORKSPACE_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    log_path.write_text(proc.stdout or "", encoding="utf-8")

    trades: List[Dict[str, Any]] = []
    payload_obj = _to_json_obj(output_json)
    if payload_obj is not None:
        trades = _strategy_trades_from_obj(payload_obj, strategy)

    output_zip = _find_latest_zip(run_dir)
    if not trades and output_zip is not None:
        trades = _load_from_zip(output_zip, strategy)

    return BacktestResult(
        exit_code=proc.returncode,
        command=cmd,
        log_path=log_path,
        output_json=output_json,
        output_zip=output_zip,
        trades=trades,
    )

