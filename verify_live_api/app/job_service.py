"""背景任務服務。"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from . import settings
from .backtest_runner import run_backtest
from .comparator import compare_signals, resolve_timerange, trades_to_signals
from .db import (
    create_job,
    get_job,
    get_profile,
    replace_compare_results,
    replace_signals,
    update_job,
    utc_now_iso,
)
from .freqtrade_client import FreqtradeApiClient, FreqtradeCredentials


def _abs_path(path_str: str) -> str:
    p = Path(path_str)
    if p.is_absolute():
        return str(p)
    return str((settings.WORKSPACE_ROOT / p).resolve())


def _profile_payload(profile_id: str) -> Dict[str, Any]:
    profile_row = get_profile(profile_id)
    if profile_row is None:
        raise ValueError(f"profile 不存在：{profile_id}")
    try:
        payload = json.loads(profile_row["payload_json"])
    except Exception as exc:
        raise ValueError("profile payload_json 格式錯誤") from exc
    if not isinstance(payload, dict):
        raise ValueError("profile payload 格式錯誤")
    return payload


def start_job(profile_id: str) -> Dict[str, Any]:
    payload = _profile_payload(profile_id)
    temp_dir = settings.RUNS_DIR / "pending"
    temp_dir.mkdir(parents=True, exist_ok=True)
    job = create_job(profile_id=profile_id, run_dir=temp_dir)
    job_id = job["job_id"]
    run_dir = settings.RUNS_DIR / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    update_job(job_id, run_dir=str(run_dir))

    t = threading.Thread(target=_execute_job, args=(job_id, payload, run_dir), daemon=True)
    t.start()
    current = get_job(job_id)
    if current is None:
        raise RuntimeError("無法取得剛建立的 job")
    return current


def _execute_job(job_id: str, payload: Dict[str, Any], run_dir: Path) -> None:
    try:
        update_job(job_id, status="running", started_at=utc_now_iso(), error="")

        start_yyyymmdd, end_yyyymmdd = resolve_timerange(
            str(payload["timerange_start"]),
            str(payload.get("timerange_end_mode", "now")),
            payload.get("timerange_end_fixed"),
        )
        timerange = f"{start_yyyymmdd}-{end_yyyymmdd}"
        update_job(
            job_id,
            resolved_timerange_start=start_yyyymmdd,
            resolved_timerange_end=end_yyyymmdd,
        )

        bt = run_backtest(
            config_path=_abs_path(str(payload["config_path"])),
            strategy=str(payload["strategy"]),
            strategy_path=_abs_path(str(payload.get("strategy_path") or "user_data/strategies")),
            timeframe=str(payload.get("timeframe") or "5m"),
            timerange=timerange,
            datadir=_abs_path(str(payload.get("datadir") or "")) if payload.get("datadir") else "",
            fee=float(payload["fee"]) if payload.get("fee") is not None else None,
            run_dir=run_dir,
        )
        update_job(job_id, backtest_exit_code=bt.exit_code)
        if not bt.ok:
            raise RuntimeError(f"回測失敗，exit_code={bt.exit_code}，請看 log：{bt.log_path}")

        backtest_signals = trades_to_signals(
            source="backtest",
            trades=bt.trades,
            timeframe=str(payload.get("timeframe") or "5m"),
            timerange_start_yyyymmdd=start_yyyymmdd,
            timerange_end_yyyymmdd=end_yyyymmdd,
            strategy_name=str(payload.get("strategy") or ""),
        )
        replace_signals(job_id, "backtest", backtest_signals)

        live_base_url = str(payload.get("live_api_base_url") or os.getenv("VERIFY_LIVE_API_BASE_URL", "")).strip()
        live_username = str(payload.get("live_api_username") or os.getenv("VERIFY_LIVE_API_USER", "")).strip()
        pwd_env_name = str(payload.get("live_api_password_env") or "VERIFY_LIVE_API_PASSWORD").strip()
        live_password = os.getenv(pwd_env_name, "")

        warning_msg = ""
        live_signals = []
        if not live_base_url or not live_username or not live_password:
            warning_msg = "略過 live 比對：Live API 連線資訊不足（請檢查 base_url/username/password_env）"
        else:
            try:
                client = FreqtradeApiClient(
                    FreqtradeCredentials(
                        base_url=live_base_url,
                        username=live_username,
                        password=live_password,
                    )
                )
                live_trades = client.fetch_all_trades(limit=500)
                open_trades = client.fetch_open_trades()
                combined_live = list(live_trades) + list(open_trades)

                live_strategy_name = str(payload.get("live_strategy_name") or payload.get("strategy") or "")
                live_signals = trades_to_signals(
                    source="live",
                    trades=combined_live,
                    timeframe=str(payload.get("timeframe") or "5m"),
                    timerange_start_yyyymmdd=start_yyyymmdd,
                    timerange_end_yyyymmdd=end_yyyymmdd,
                    strategy_name=live_strategy_name,
                )
            except Exception as live_exc:
                warning_msg = f"略過 live 比對：{live_exc}"

        replace_signals(job_id, "live", live_signals)

        compare_rows = compare_signals(
            backtest_signals=backtest_signals,
            live_signals=live_signals,
            price_tolerance_bps=float(payload.get("price_tolerance_bps") or settings.DEFAULT_PRICE_TOL_BPS),
            qty_tolerance_ratio=float(payload.get("qty_tolerance_ratio") or settings.DEFAULT_QTY_TOL_RATIO),
        )
        replace_compare_results(job_id, compare_rows)

        update_job(job_id, status="completed", finished_at=utc_now_iso(), error=warning_msg)
    except Exception as exc:
        update_job(job_id, status="failed", finished_at=utc_now_iso(), error=str(exc))
