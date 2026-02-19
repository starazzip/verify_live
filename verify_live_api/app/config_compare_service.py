"""Local config 與 Live show_config 比對服務。"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import settings
from .config_loader import load_config_dict
from .db import get_profile
from .freqtrade_client import FreqtradeApiClient, FreqtradeCredentials

MISSING = object()


def _load_profile_payload(profile_id: str) -> Dict[str, Any]:
    row = get_profile(profile_id)
    if row is None:
        raise ValueError(f"找不到 profile_id：{profile_id}")
    try:
        payload = json.loads(row["payload_json"])
    except Exception as exc:
        raise ValueError("profile payload_json 格式錯誤") from exc
    if not isinstance(payload, dict):
        raise ValueError("profile payload 格式錯誤")
    return payload


def _get_nested(data: Any, path: str) -> Any:
    cur = data
    for token in path.split("."):
        if not isinstance(cur, dict):
            return MISSING
        if token not in cur:
            return MISSING
        cur = cur[token]
    return cur


def _canon(value: Any, *, exchange_name: bool = False) -> Any:
    if value is MISSING:
        return MISSING
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip()
        return v.lower() if exchange_name else v
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def _present_value(value: Any) -> Any:
    if value is MISSING:
        return None
    return value


def _as_str_list(value: Any) -> List[str]:
    if value is MISSING or value is None:
        return []
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _build_local_effective_config(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    config_path = str(payload.get("config_path") or "").strip()
    if not config_path:
        raise ValueError("profile 缺少 config_path")
    abs_config_path = settings.resolve_project_path(config_path)
    if not abs_config_path.exists():
        raise ValueError(f"找不到本地 config：{abs_config_path}")

    cfg = load_config_dict(abs_config_path)
    local_cfg = copy.deepcopy(cfg)

    if str(payload.get("strategy") or "").strip():
        local_cfg["strategy"] = str(payload["strategy"]).strip()
    if str(payload.get("timeframe") or "").strip():
        local_cfg["timeframe"] = str(payload["timeframe"]).strip()
    if payload.get("fee") is not None:
        try:
            local_cfg["fee"] = float(payload["fee"])
        except Exception:
            local_cfg["fee"] = payload["fee"]
    if str(payload.get("datadir") or "").strip():
        local_cfg["datadir"] = str(payload["datadir"]).strip()

    return local_cfg, str(abs_config_path)


def _field_specs() -> List[Dict[str, str]]:
    return [
        {"field": "strategy", "local": "strategy", "live": "strategy"},
        {"field": "timeframe", "local": "timeframe", "live": "timeframe"},
        {"field": "trading_mode", "local": "trading_mode", "live": "trading_mode"},
        {"field": "exchange", "local": "exchange.name", "live": "exchange"},
        {"field": "bot_name", "local": "bot_name", "live": "bot_name"},
        {"field": "stake_currency", "local": "stake_currency", "live": "stake_currency"},
        {"field": "stake_amount", "local": "stake_amount", "live": "stake_amount"},
        {"field": "max_open_trades", "local": "max_open_trades", "live": "max_open_trades"},
        {"field": "stoploss", "local": "stoploss", "live": "stoploss"},
        {"field": "trailing_stop", "local": "trailing_stop", "live": "trailing_stop"},
        {"field": "trailing_stop_positive", "local": "trailing_stop_positive", "live": "trailing_stop_positive"},
        {
            "field": "trailing_stop_positive_offset",
            "local": "trailing_stop_positive_offset",
            "live": "trailing_stop_positive_offset",
        },
        {
            "field": "trailing_only_offset_is_reached",
            "local": "trailing_only_offset_is_reached",
            "live": "trailing_only_offset_is_reached",
        },
        {"field": "process_only_new_candles", "local": "process_only_new_candles", "live": "process_only_new_candles"},
        {"field": "use_exit_signal", "local": "use_exit_signal", "live": "use_exit_signal"},
        {"field": "exit_profit_only", "local": "exit_profit_only", "live": "exit_profit_only"},
        {
            "field": "ignore_roi_if_entry_signal",
            "local": "ignore_roi_if_entry_signal",
            "live": "ignore_roi_if_entry_signal",
        },
        {"field": "startup_candle_count", "local": "startup_candle_count", "live": "startup_candle_count"},
        {"field": "can_short", "local": "can_short", "live": "short_allowed"},
        {"field": "order_types.entry", "local": "order_types.entry", "live": "order_types.entry"},
        {"field": "order_types.exit", "local": "order_types.exit", "live": "order_types.exit"},
        {"field": "order_types.stoploss", "local": "order_types.stoploss", "live": "order_types.stoploss"},
        {"field": "order_time_in_force.entry", "local": "order_time_in_force.entry", "live": "order_time_in_force.entry"},
        {"field": "order_time_in_force.exit", "local": "order_time_in_force.exit", "live": "order_time_in_force.exit"},
        {"field": "entry_pricing.price_side", "local": "entry_pricing.price_side", "live": "entry_pricing.price_side"},
        {"field": "exit_pricing.price_side", "local": "exit_pricing.price_side", "live": "exit_pricing.price_side"},
        {"field": "unfilledtimeout.entry", "local": "unfilledtimeout.entry", "live": "unfilledtimeout.entry"},
        {"field": "unfilledtimeout.exit", "local": "unfilledtimeout.exit", "live": "unfilledtimeout.exit"},
    ]


def _documented_live_not_provided_paths() -> set[str]:
    # 依 Freqtrade 官方 show_config 回傳欄位（rpc._rpc_show_config / ShowConfig schema）整理。
    # 這些欄位不在 show_config 回傳結構內，應標記為「Live不提供」而非缺失。
    return {
        "process_only_new_candles",
        "use_exit_signal",
        "exit_profit_only",
        "ignore_roi_if_entry_signal",
        "startup_candle_count",
        "order_time_in_force.entry",
        "order_time_in_force.exit",
    }


def _build_row_reason(
    *,
    status: str,
    field_name: str,
    local_path: str,
    live_path: str,
) -> str:
    if status == "not_provided_live":
        return f"LIVE不提供：`show_config` 不回傳 `{live_path}`。"
    if status == "missing_live":
        return (
            f"Live `show_config` 未回傳 `{live_path}`。"
            "遠端 API 僅提供與交易運行相關的部分設定，可能不含所有原始 config 欄位。"
        )
    if status == "missing_local":
        return f"Local config 未設定 `{local_path}`。"
    if status == "mismatch":
        return f"`{field_name}` Local 與 Live 值不一致。"
    if status == "match":
        return "Local 與 Live 一致。"
    if status == "ignored":
        return "此欄位僅供參考，不納入一致性判定。"
    return "-"


def compare_profile_vs_live_config(profile_id: str) -> Dict[str, Any]:
    payload = _load_profile_payload(profile_id)
    local_cfg, resolved_config_path = _build_local_effective_config(payload)

    live_base_url = str(payload.get("live_api_base_url") or os.getenv("VERIFY_LIVE_API_BASE_URL", "")).strip()
    live_username = str(payload.get("live_api_username") or os.getenv("VERIFY_LIVE_API_USER", "")).strip()
    live_password = str(payload.get("live_api_password") or os.getenv("VERIFY_LIVE_API_PASSWORD", "")).strip()
    if not live_base_url or not live_username or not live_password:
        raise ValueError("Live API 連線資訊不足（請檢查 base_url/username/password）")

    client = FreqtradeApiClient(
        FreqtradeCredentials(
            base_url=live_base_url,
            username=live_username,
            password=live_password,
        )
    )
    live_cfg = client.fetch_show_config()
    live_whitelist = client.fetch_whitelist()
    live_blacklist = client.fetch_blacklist()
    live_not_provided_paths = _documented_live_not_provided_paths()

    rows: List[Dict[str, Any]] = []
    summary = {
        "total": 0,
        "match": 0,
        "mismatch": 0,
        "missing_live": 0,
        "missing_local": 0,
        "not_provided_live": 0,
    }
    for spec in _field_specs():
        live_path = spec["live"]
        local_raw = _get_nested(local_cfg, spec["local"])
        if live_path in live_not_provided_paths:
            live_raw = MISSING
            live_unavailable_by_design = True
        else:
            live_raw = _get_nested(live_cfg, live_path)
            live_unavailable_by_design = False
        if local_raw is MISSING and live_raw is MISSING:
            continue

        is_exchange_field = spec["field"] == "exchange"
        local_norm = _canon(local_raw, exchange_name=is_exchange_field)
        live_norm = _canon(live_raw, exchange_name=is_exchange_field)

        if local_raw is MISSING:
            status = "missing_local"
        elif live_unavailable_by_design:
            status = "not_provided_live"
        elif live_raw is MISSING:
            status = "missing_live"
        elif local_norm == live_norm:
            status = "match"
        else:
            status = "mismatch"

        summary["total"] += 1
        summary[status] += 1
        rows.append(
            {
                "field": spec["field"],
                "local_value": _present_value(local_raw),
                "live_value": _present_value(live_raw),
                "status": status,
                "reason": _build_row_reason(
                    status=status,
                    field_name=spec["field"],
                    local_path=spec["local"],
                    live_path=live_path,
                ),
            }
        )

    local_whitelist = _as_str_list(_get_nested(local_cfg, "exchange.pair_whitelist"))
    local_blacklist = _as_str_list(_get_nested(local_cfg, "exchange.pair_blacklist"))

    wl_only_local = sorted(set(local_whitelist) - set(live_whitelist))
    wl_only_live = sorted(set(live_whitelist) - set(local_whitelist))
    bl_only_local = sorted(set(local_blacklist) - set(live_blacklist))
    bl_only_live = sorted(set(live_blacklist) - set(local_blacklist))

    # 白名單只做資訊揭露，不列入一致性硬條件。
    wl_status = "ignored"
    bl_status = "match" if not bl_only_local and not bl_only_live else "mismatch"

    rows.extend(
        [
            {
                "field": "exchange.pair_whitelist.count",
                "local_value": len(local_whitelist),
                "live_value": len(live_whitelist),
                "status": wl_status,
                "reason": _build_row_reason(
                    status=wl_status,
                    field_name="exchange.pair_whitelist.count",
                    local_path="exchange.pair_whitelist",
                    live_path="whitelist",
                ),
            },
            {
                "field": "exchange.pair_blacklist.count",
                "local_value": len(local_blacklist),
                "live_value": len(live_blacklist),
                "status": bl_status,
                "reason": _build_row_reason(
                    status=bl_status,
                    field_name="exchange.pair_blacklist.count",
                    local_path="exchange.pair_blacklist",
                    live_path="blacklist",
                ),
            },
        ]
    )
    if wl_status in summary:
        summary["total"] += 1
        summary[wl_status] += 1
    if bl_status in summary:
        summary["total"] += 1
    summary[bl_status] += 1

    return {
        "profile_id": profile_id,
        "resolved_config_path": resolved_config_path,
        "live_api_base_url": live_base_url,
        "summary": summary,
        "pairlist_compare": {
            "whitelist": {
                "status": wl_status,
                "enforced": False,
                "local_count": len(local_whitelist),
                "live_count": len(live_whitelist),
                "only_local_count": len(wl_only_local),
                "only_live_count": len(wl_only_live),
                "only_local_sample": wl_only_local[:50],
                "only_live_sample": wl_only_live[:50],
            },
            "blacklist": {
                "status": bl_status,
                "enforced": True,
                "local_count": len(local_blacklist),
                "live_count": len(live_blacklist),
                "only_local_count": len(bl_only_local),
                "only_live_count": len(bl_only_live),
                "only_local_sample": bl_only_local[:50],
                "only_live_sample": bl_only_live[:50],
            },
        },
        "items": rows,
    }
