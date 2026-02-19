"""背景任務服務。"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import settings
from .backtest_runner import run_backtest
from .comparator import build_freqtrade_timerange, compare_signals, resolve_timerange, trades_to_signals
from .db import (
    create_job,
    get_job,
    is_job_cancel_requested,
    get_profile,
    replace_compare_results,
    replace_signals,
    update_job,
    utc_now_iso,
)
from .freqtrade_client import FreqtradeApiClient, FreqtradeCredentials


def _abs_path(path_str: str) -> str:
    return str(settings.resolve_project_path(path_str))


def _normalize_strategy_dir(path_str: str) -> Path:
    path = settings.resolve_project_path(path_str)
    if path.suffix.lower() == ".py":
        return path.parent
    return path


def _path_has_strategy_class(path: Path, strategy_name: str) -> bool:
    if not path.exists():
        return False
    regex = re.compile(rf"^\s*class\s+{re.escape(strategy_name)}\b", re.MULTILINE)
    files = [path] if path.is_file() and path.suffix.lower() == ".py" else sorted(path.glob("*.py"))
    for pyfile in files:
        try:
            text = pyfile.read_text(encoding="utf-8")
        except Exception:
            continue
        if regex.search(text):
            return True
    return False


def _resolve_strategy_path(strategy_name: str, preferred_path: str, userdir: Path) -> str:
    preferred_dir = _normalize_strategy_dir(preferred_path)
    if _path_has_strategy_class(preferred_dir, strategy_name):
        return str(preferred_dir)

    candidates = [preferred_dir, (userdir / "strategies").resolve()]
    for item in userdir.rglob("strategies"):
        if not item.is_dir():
            continue
        # 限縮搜尋深度，避免掃描過慢。
        if len(item.relative_to(userdir).parts) > 3:
            continue
        candidates.append(item.resolve())

    seen = set()
    for cand in candidates:
        cand_resolved = cand.resolve()
        if cand_resolved in seen:
            continue
        seen.add(cand_resolved)
        if _path_has_strategy_class(cand_resolved, strategy_name):
            return str(cand_resolved)
    return str(preferred_dir)


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


def _signal_key(item: Dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("pair") or ""),
        str(item.get("side") or ""),
        str(item.get("signal_ts") or ""),
        str(item.get("trade_id") or ""),
        str(item.get("strategy") or ""),
    )


def _build_live_strategy_filter_warning(
    *,
    filtered_signals: List[Dict[str, Any]],
    all_signals: List[Dict[str, Any]],
    strategy_name: str,
) -> str:
    if not strategy_name:
        return ""
    filtered_keys = {_signal_key(item) for item in filtered_signals}
    dropped = [item for item in all_signals if _signal_key(item) not in filtered_keys]
    if not dropped:
        return ""

    dropped_trade_ids = {str(item.get("trade_id") or "") for item in dropped if str(item.get("trade_id") or "").strip()}
    pair_strategy_counter: Dict[str, int] = {}
    for item in dropped:
        pair = str(item.get("pair") or "-")
        strategy = str(item.get("strategy") or "-")
        key = f"{pair} ({strategy})"
        pair_strategy_counter[key] = pair_strategy_counter.get(key, 0) + 1
    top_samples = sorted(pair_strategy_counter.items(), key=lambda x: (-x[1], x[0]))[:5]
    sample_text = ", ".join([f"{name} x{cnt}" for name, cnt in top_samples]) if top_samples else "-"
    return (
        f"偵測到 live 歷史交易含其他策略（目前比對策略：{strategy_name}），"
        f"已排除 {len(dropped)} 筆訊號（{len(dropped_trade_ids)} 筆交易），樣本：{sample_text}。"
        "通常是策略切換後殘留的歷史成交。"
    )


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
        if is_job_cancel_requested(job_id):
            update_job(job_id, status="cancelled", finished_at=utc_now_iso(), error="任務已由使用者停止")
            return
        update_job(job_id, status="running", started_at=utc_now_iso(), error="")

        start_yyyymmdd, end_yyyymmdd = resolve_timerange(
            str(payload["timerange_start"]),
            str(payload.get("timerange_end_mode", "now")),
            payload.get("timerange_end_fixed"),
        )
        # freqtrade 的日期結束預設會落在當天 00:00，這裡改成「含結束日整天」。
        timerange = build_freqtrade_timerange(start_yyyymmdd, end_yyyymmdd, include_end_day=True)
        update_job(
            job_id,
            resolved_timerange_start=start_yyyymmdd,
            resolved_timerange_end=end_yyyymmdd,
        )
        if is_job_cancel_requested(job_id):
            update_job(job_id, status="cancelled", finished_at=utc_now_iso(), error="任務已由使用者停止")
            return

        config_path = _abs_path(str(payload["config_path"]))
        strategy_path = _abs_path(str(payload.get("strategy_path") or "user_data/strategies"))
        datadir = _abs_path(str(payload.get("datadir") or "")) if payload.get("datadir") else ""
        userdir = settings.resolve_userdir([config_path, strategy_path, datadir])
        if userdir is None:
            raise RuntimeError(
                "找不到可用的 user_data 目錄。請確認 verify_live 與 user_data 同層，"
                "或在 .env 設定 VERIFY_LIVE_WORKSPACE_ROOT。"
            )
        strategy_path = _resolve_strategy_path(str(payload["strategy"]), strategy_path, userdir)

        live_base_url = str(payload.get("live_api_base_url") or os.getenv("VERIFY_LIVE_API_BASE_URL", "")).strip()
        live_username = str(payload.get("live_api_username") or os.getenv("VERIFY_LIVE_API_USER", "")).strip()
        live_password = str(payload.get("live_api_password") or os.getenv("VERIFY_LIVE_API_PASSWORD", "")).strip()

        warning_parts: List[str] = []
        live_client: Optional[FreqtradeApiClient] = None
        live_whitelist: Optional[List[str]] = None
        live_config_strategy = ""
        if live_base_url and live_username and live_password:
            try:
                live_client = FreqtradeApiClient(
                    FreqtradeCredentials(
                        base_url=live_base_url,
                        username=live_username,
                        password=live_password,
                    )
                )
                live_cfg = live_client.fetch_show_config()
                live_config_strategy = str(live_cfg.get("strategy") or "").strip()
                live_whitelist = live_client.fetch_whitelist()
                if not live_whitelist:
                    warning_parts.append("未取得 live whitelist 快照，回測改用 config pairlist")
            except Exception as wl_exc:
                warning_parts.append(f"未取得 live whitelist 快照：{wl_exc}")
                live_client = None

        expected_live_strategy = str(payload.get("live_strategy_name") or payload.get("strategy") or "").strip()
        if expected_live_strategy and live_config_strategy and live_config_strategy != expected_live_strategy:
            raise RuntimeError(
                f"Live 目前策略為 {live_config_strategy}，與期望 {expected_live_strategy} 不一致。"
                "請先確認實盤容器是否已套用正確策略後再驗證。"
            )

        bt = run_backtest(
            config_path=config_path,
            strategy=str(payload["strategy"]),
            strategy_path=strategy_path,
            timeframe=str(payload.get("timeframe") or "5m"),
            timerange=timerange,
            datadir=datadir,
            userdir=str(userdir),
            fee=float(payload["fee"]) if payload.get("fee") is not None else None,
            run_dir=run_dir,
            should_cancel=lambda: is_job_cancel_requested(job_id),
            pairs=live_whitelist or None,
        )
        update_job(job_id, backtest_exit_code=bt.exit_code)
        if bt.cancelled or is_job_cancel_requested(job_id):
            update_job(job_id, status="cancelled", finished_at=utc_now_iso(), error="任務已由使用者停止")
            return
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
        if is_job_cancel_requested(job_id):
            update_job(job_id, status="cancelled", finished_at=utc_now_iso(), error="任務已由使用者停止")
            return

        live_signals = []
        if not live_base_url or not live_username or not live_password:
            warning_parts.append("略過 live 比對：Live API 連線資訊不足（請檢查 base_url/username/password）")
        else:
            try:
                client = live_client or FreqtradeApiClient(
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
                all_live_signals = trades_to_signals(
                    source="live",
                    trades=combined_live,
                    timeframe=str(payload.get("timeframe") or "5m"),
                    timerange_start_yyyymmdd=start_yyyymmdd,
                    timerange_end_yyyymmdd=end_yyyymmdd,
                    strategy_name="",
                )
                live_signals = trades_to_signals(
                    source="live",
                    trades=combined_live,
                    timeframe=str(payload.get("timeframe") or "5m"),
                    timerange_start_yyyymmdd=start_yyyymmdd,
                    timerange_end_yyyymmdd=end_yyyymmdd,
                    strategy_name=live_strategy_name,
                )
                strategy_filter_warning = _build_live_strategy_filter_warning(
                    filtered_signals=live_signals,
                    all_signals=all_live_signals,
                    strategy_name=live_strategy_name,
                )
                if strategy_filter_warning:
                    warning_parts.append(strategy_filter_warning)
            except Exception as live_exc:
                warning_parts.append(f"略過 live 比對：{live_exc}")

        replace_signals(job_id, "live", live_signals)
        if is_job_cancel_requested(job_id):
            update_job(job_id, status="cancelled", finished_at=utc_now_iso(), error="任務已由使用者停止")
            return

        compare_rows = compare_signals(
            backtest_signals=backtest_signals,
            live_signals=live_signals,
            price_tolerance_bps=float(payload.get("price_tolerance_bps") or settings.DEFAULT_PRICE_TOL_BPS),
            qty_tolerance_ratio=float(payload.get("qty_tolerance_ratio") or settings.DEFAULT_QTY_TOL_RATIO),
        )
        replace_compare_results(job_id, compare_rows)

        update_job(
            job_id,
            status="completed",
            finished_at=utc_now_iso(),
            error="; ".join([w for w in warning_parts if w]),
        )
    except Exception as exc:
        update_job(job_id, status="failed", finished_at=utc_now_iso(), error=str(exc))
