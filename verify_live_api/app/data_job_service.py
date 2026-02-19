"""K 線資料下載背景任務。"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List

from . import settings
from .comparator import build_freqtrade_timerange, resolve_timerange
from .db import (
    create_data_job,
    get_data_job,
    get_profile,
    init_db,
    update_data_job,
    utc_now_iso,
)
from .process_runner import run_command_with_live_log


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


def _parse_timeframes(raw: Any) -> List[str]:
    if raw is None:
        return []
    tokens: List[str]
    if isinstance(raw, list):
        tokens = [str(x) for x in raw]
    elif isinstance(raw, str):
        tokens = raw.replace(";", ",").split(",")
    else:
        return []
    result: List[str] = []
    for token in tokens:
        tf = str(token).strip()
        if tf and tf not in result:
            result.append(tf)
    return result


def _resolve_download_timeframes(primary_timeframe: str, requested_timeframes: Any) -> List[str]:
    primary = str(primary_timeframe or "5m").strip() or "5m"
    requested = _parse_timeframes(requested_timeframes)
    if requested:
        ordered = [primary, *requested]
    else:
        raw_extra = str(getattr(settings, "DOWNLOAD_EXTRA_TIMEFRAMES", "4h,1d"))
        extras: List[str] = []
        for token in raw_extra.replace(";", ",").split(","):
            tf = token.strip()
            if tf:
                extras.append(tf)
        ordered = [primary, *extras]
    uniq: List[str] = []
    for tf in ordered:
        if tf not in uniq:
            uniq.append(tf)
    return uniq


def _append_log(log_path: Path, text: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def start_data_job(profile_id: str) -> Dict[str, Any]:
    init_db()
    payload = _profile_payload(profile_id)
    temp_dir = settings.RUNS_DIR / "pending_data"
    temp_dir.mkdir(parents=True, exist_ok=True)
    row = create_data_job(profile_id=profile_id, run_dir=temp_dir)
    data_job_id = row["data_job_id"]
    run_dir = settings.RUNS_DIR / data_job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    update_data_job(data_job_id, run_dir=str(run_dir))

    t = threading.Thread(target=_execute_data_job, args=(data_job_id, payload, run_dir), daemon=True)
    t.start()
    current = get_data_job(data_job_id)
    if current is None:
        raise RuntimeError("無法取得剛建立的 data_job")
    return current


def _execute_data_job(data_job_id: str, payload: Dict[str, Any], run_dir: Path) -> None:
    try:
        update_data_job(data_job_id, status="running", started_at=utc_now_iso(), error="")
        start_yyyymmdd, end_yyyymmdd = resolve_timerange(
            str(payload["timerange_start"]),
            str(payload.get("timerange_end_mode", "now")),
            payload.get("timerange_end_fixed"),
        )
        timeframe = str(payload.get("timeframe") or "5m")
        timeframes = _resolve_download_timeframes(timeframe, payload.get("download_timeframes"))
        timerange = build_freqtrade_timerange(start_yyyymmdd, end_yyyymmdd, include_end_day=True)
        update_data_job(
            data_job_id,
            resolved_timerange_start=start_yyyymmdd,
            resolved_timerange_end=end_yyyymmdd,
            timeframe=",".join(timeframes),
        )

        config_path = str(settings.resolve_project_path(str(payload["config_path"])))
        strategy_path = str(settings.resolve_project_path(str(payload.get("strategy_path") or "user_data/strategies")))
        datadir = str(settings.resolve_project_path(str(payload.get("datadir") or ""))) if payload.get("datadir") else ""
        userdir = settings.resolve_userdir([config_path, strategy_path, datadir])
        if userdir is None:
            raise RuntimeError(
                "找不到可用的 user_data 目錄。請確認 verify_live 與 user_data 同層，"
                "或在 .env 設定 VERIFY_LIVE_WORKSPACE_ROOT。"
            )

        base_cmd = [
            settings.FREQTRADE_BIN,
            "download-data",
            "--userdir",
            str(userdir),
            "--config",
            config_path,
            "--timeframes",
            *timeframes,
            "--timerange",
            timerange,
            "--include-inactive-pairs",
            "--data-format-ohlcv",
            "feather",
        ]
        if datadir:
            base_cmd += ["--datadir", datadir]

        append_cmd = list(base_cmd)
        prepend_cmd = [*base_cmd, "--prepend"]

        log_path = run_dir / "download_data.log"
        if log_path.exists():
            log_path.unlink()

        # 先執行 prepend 補舊資料，再以 append 收尾補最新資料，
        # 避免某些情境下 prepend 寫回舊資料邊界造成最新 K 線被覆蓋。
        _append_log(log_path, f"[verify_live] [1/2] prepend 模式下載（timeframes={','.join(timeframes)}）")
        prepend_result = run_command_with_live_log(
            cmd=prepend_cmd,
            cwd=settings.WORKSPACE_ROOT,
            log_path=log_path,
            append=True,
        )
        if prepend_result.exit_code != 0:
            update_data_job(
                data_job_id,
                exit_code=prepend_result.exit_code,
                command_json=json.dumps({"append_cmd": append_cmd, "prepend_cmd": prepend_cmd}, ensure_ascii=False),
            )
            raise RuntimeError(f"K 線更新失敗（prepend），exit_code={prepend_result.exit_code}，請看 log：{log_path}")

        _append_log(log_path, f"[verify_live] [2/2] append 模式下載（timeframes={','.join(timeframes)}）")
        append_result = run_command_with_live_log(
            cmd=append_cmd,
            cwd=settings.WORKSPACE_ROOT,
            log_path=log_path,
            append=True,
        )
        final_exit_code = append_result.exit_code
        update_data_job(
            data_job_id,
            exit_code=final_exit_code,
            command_json=json.dumps({"append_cmd": append_cmd, "prepend_cmd": prepend_cmd}, ensure_ascii=False),
        )

        if final_exit_code != 0:
            raise RuntimeError(f"K 線更新失敗（append），exit_code={final_exit_code}，請看 log：{log_path}")

        update_data_job(data_job_id, status="completed", finished_at=utc_now_iso(), error="")
    except Exception as exc:
        update_data_job(data_job_id, status="failed", finished_at=utc_now_iso(), error=str(exc))
