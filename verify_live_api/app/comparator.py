"""訊號與成交比對邏輯。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _parse_iso_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _parse_timerange_date(date_yyyymmdd: str) -> datetime:
    dt = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    return dt.replace(tzinfo=timezone.utc)


def resolve_timerange(start_yyyymmdd: str, end_mode: str, end_fixed: Optional[str]) -> Tuple[str, str]:
    start_dt = _parse_timerange_date(start_yyyymmdd)
    if end_mode == "now":
        end_dt = datetime.now(tz=timezone.utc)
    else:
        if not end_fixed:
            raise ValueError("timerange_end_mode=fixed 但未提供 timerange_end_fixed")
        end_dt = _parse_timerange_date(end_fixed).replace(hour=23, minute=59, second=59)
    if end_dt < start_dt:
        raise ValueError("timerange_end 不能早於 timerange_start")
    return start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")


def _timeframe_to_seconds(timeframe: str) -> int:
    tf = timeframe.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1]) * 60
    if tf.endswith("h"):
        return int(tf[:-1]) * 3600
    if tf.endswith("d"):
        return int(tf[:-1]) * 86400
    raise ValueError(f"不支援的 timeframe：{timeframe}")


def _floor_bucket(dt: datetime, timeframe: str) -> datetime:
    seconds = _timeframe_to_seconds(timeframe)
    ts = int(dt.timestamp())
    floored = ts - (ts % seconds)
    return datetime.fromtimestamp(floored, tz=timezone.utc)


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def trades_to_signals(
    *,
    source: str,
    trades: List[Dict[str, Any]],
    timeframe: str,
    timerange_start_yyyymmdd: str,
    timerange_end_yyyymmdd: str,
    strategy_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    start_dt = _parse_timerange_date(timerange_start_yyyymmdd)
    end_dt = _parse_timerange_date(timerange_end_yyyymmdd).replace(hour=23, minute=59, second=59)

    signals: List[Dict[str, Any]] = []
    for t in trades:
        pair = str(t.get("pair") or t.get("symbol") or "").strip()
        if not pair:
            continue
        trade_strategy = str(t.get("strategy") or "").strip()
        if strategy_name and trade_strategy and trade_strategy != strategy_name:
            continue
        trade_id = str(t.get("trade_id") or t.get("id") or "")
        amount = _safe_float(t.get("amount") or t.get("amount_requested") or t.get("stake_amount"))

        open_dt = _parse_iso_dt(t.get("open_date_utc") or t.get("open_date"))
        close_dt = _parse_iso_dt(t.get("close_date_utc") or t.get("close_date"))

        open_rate = _safe_float(t.get("open_rate"))
        close_rate = _safe_float(t.get("close_rate"))
        enter_tag = str(t.get("enter_tag") or "")
        exit_reason = str(t.get("exit_reason") or "")

        if open_dt and start_dt <= open_dt <= end_dt:
            bucket = _floor_bucket(open_dt, timeframe)
            signals.append(
                {
                    "source": source,
                    "pair": pair,
                    "side": "entry",
                    "bucket_ts": bucket.isoformat(),
                    "signal_ts": open_dt.isoformat(),
                    "price": open_rate,
                    "amount": amount,
                    "enter_tag": enter_tag,
                    "exit_reason": "",
                    "trade_id": trade_id,
                    "strategy": trade_strategy,
                    "raw_payload": t,
                }
            )

        if close_dt and start_dt <= close_dt <= end_dt:
            bucket = _floor_bucket(close_dt, timeframe)
            signals.append(
                {
                    "source": source,
                    "pair": pair,
                    "side": "exit",
                    "bucket_ts": bucket.isoformat(),
                    "signal_ts": close_dt.isoformat(),
                    "price": close_rate,
                    "amount": amount,
                    "enter_tag": enter_tag,
                    "exit_reason": exit_reason,
                    "trade_id": trade_id,
                    "strategy": trade_strategy,
                    "raw_payload": t,
                }
            )

    signals.sort(key=lambda x: (x["pair"], x["side"], x["bucket_ts"], x["signal_ts"], x["trade_id"]))
    return signals


def _group_by_key(signals: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    for item in signals:
        key = (str(item.get("pair")), str(item.get("side")), str(item.get("bucket_ts")))
        groups[key].append(item)
    for items in groups.values():
        items.sort(key=lambda x: (x.get("signal_ts", ""), x.get("trade_id", "")))
    return groups


def _price_diff_bps(bt_price: Optional[float], live_price: Optional[float]) -> Optional[float]:
    if bt_price in (None, 0) or live_price is None:
        return None
    return abs(float(live_price) - float(bt_price)) / abs(float(bt_price)) * 10000.0


def _qty_diff_ratio(bt_amount: Optional[float], live_amount: Optional[float]) -> Optional[float]:
    if bt_amount in (None, 0) or live_amount is None:
        return None
    return abs(float(live_amount) - float(bt_amount)) / abs(float(bt_amount))


def compare_signals(
    *,
    backtest_signals: List[Dict[str, Any]],
    live_signals: List[Dict[str, Any]],
    price_tolerance_bps: float,
    qty_tolerance_ratio: float,
) -> List[Dict[str, Any]]:
    bt_groups = _group_by_key(backtest_signals)
    live_groups = _group_by_key(live_signals)
    all_keys = sorted(set(bt_groups.keys()) | set(live_groups.keys()))

    rows: List[Dict[str, Any]] = []
    for pair, side, bucket_ts in all_keys:
        bt_items = bt_groups.get((pair, side, bucket_ts), [])
        live_items = live_groups.get((pair, side, bucket_ts), [])
        size = max(len(bt_items), len(live_items))

        for idx in range(size):
            bt = bt_items[idx] if idx < len(bt_items) else None
            lv = live_items[idx] if idx < len(live_items) else None

            if bt is None:
                rows.append(
                    {
                        "pair": pair,
                        "side": side,
                        "bucket_ts": bucket_ts,
                        "signal_lamp": "red",
                        "fill_lamp": "red",
                        "signal_state": "MISSING_IN_BACKTEST",
                        "price_state": "N/A",
                        "qty_state": "N/A",
                        "bt_signal_ts": "",
                        "live_signal_ts": lv.get("signal_ts", ""),
                        "bt_price": None,
                        "live_price": lv.get("price"),
                        "price_diff_bps": None,
                        "bt_amount": None,
                        "live_amount": lv.get("amount"),
                        "qty_diff_ratio": None,
                        "reason": "同根 K 僅有 live 訊號",
                    }
                )
                continue

            if lv is None:
                rows.append(
                    {
                        "pair": pair,
                        "side": side,
                        "bucket_ts": bucket_ts,
                        "signal_lamp": "red",
                        "fill_lamp": "red",
                        "signal_state": "MISSING_IN_LIVE",
                        "price_state": "N/A",
                        "qty_state": "N/A",
                        "bt_signal_ts": bt.get("signal_ts", ""),
                        "live_signal_ts": "",
                        "bt_price": bt.get("price"),
                        "live_price": None,
                        "price_diff_bps": None,
                        "bt_amount": bt.get("amount"),
                        "live_amount": None,
                        "qty_diff_ratio": None,
                        "reason": "同根 K 僅有 backtest 訊號",
                    }
                )
                continue

            bt_price = _safe_float(bt.get("price"))
            lv_price = _safe_float(lv.get("price"))
            bt_amount = _safe_float(bt.get("amount"))
            lv_amount = _safe_float(lv.get("amount"))

            p_diff = _price_diff_bps(bt_price, lv_price)
            q_diff = _qty_diff_ratio(bt_amount, lv_amount)
            price_state = "MATCH" if p_diff is not None and p_diff <= price_tolerance_bps else "MISMATCH"
            qty_state = "MATCH" if q_diff is not None and q_diff <= qty_tolerance_ratio else "MISMATCH"

            fill_lamp = "green" if (price_state == "MATCH" and qty_state == "MATCH") else "yellow"
            reason = "價量一致" if fill_lamp == "green" else "時點一致但價量超出容忍"

            rows.append(
                {
                    "pair": pair,
                    "side": side,
                    "bucket_ts": bucket_ts,
                    "signal_lamp": "green",
                    "fill_lamp": fill_lamp,
                    "signal_state": "MATCH_SAME_BUCKET",
                    "price_state": price_state,
                    "qty_state": qty_state,
                    "bt_signal_ts": bt.get("signal_ts", ""),
                    "live_signal_ts": lv.get("signal_ts", ""),
                    "bt_price": bt_price,
                    "live_price": lv_price,
                    "price_diff_bps": p_diff,
                    "bt_amount": bt_amount,
                    "live_amount": lv_amount,
                    "qty_diff_ratio": q_diff,
                    "reason": reason,
                }
            )

    return rows

