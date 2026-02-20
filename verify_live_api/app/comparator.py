"""訊號與成交比對邏輯。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

IGNORED_TAIL_FORCE_EXIT = "IGNORED_TAIL_FORCE_EXIT"


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


def _parse_epoch_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        num = float(text)
    except Exception:
        return None
    if not (num == num):  # NaN
        return None
    # 大於 10^11 視為毫秒時間戳，小於則視為秒。
    ts_seconds = num / 1000.0 if abs(num) >= 1e11 else num
    try:
        return datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
    except Exception:
        return None


def _parse_trade_event_dt(trade: Dict[str, Any], side: str) -> Optional[datetime]:
    if side == "entry":
        candidates = [
            trade.get("open_timestamp"),
            trade.get("open_fill_timestamp"),
            trade.get("open_date_utc"),
            trade.get("open_date"),
        ]
    else:
        candidates = [
            trade.get("close_timestamp"),
            trade.get("close_date_utc"),
            trade.get("close_date"),
        ]
    for candidate in candidates:
        dt = _parse_epoch_dt(candidate) or _parse_iso_dt(candidate)
        if dt is not None:
            return dt
    return None


def _iso_millis(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds")


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


def build_freqtrade_timerange(start_yyyymmdd: str, end_yyyymmdd: str, *, include_end_day: bool = True) -> str:
    start_dt = _parse_timerange_date(start_yyyymmdd)
    end_dt = _parse_timerange_date(end_yyyymmdd)
    if include_end_day:
        end_dt = end_dt + timedelta(days=1)
    if end_dt <= start_dt:
        raise ValueError("freqtrade timerange 結束時間需晚於開始時間")
    return f"{start_dt.strftime('%Y%m%d')}-{end_dt.strftime('%Y%m%d')}"


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


def _is_same_second(ts_a: str, ts_b: str) -> bool:
    dt_a = _parse_iso_dt(ts_a)
    dt_b = _parse_iso_dt(ts_b)
    if dt_a is None or dt_b is None:
        return bool(ts_a) and ts_a == ts_b
    return int(dt_a.timestamp()) == int(dt_b.timestamp())


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

        open_dt = _parse_trade_event_dt(t, "entry")
        close_dt = _parse_trade_event_dt(t, "exit")

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
                    "signal_ts": _iso_millis(open_dt),
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
                    "signal_ts": _iso_millis(close_dt),
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


def _is_strategy_mismatch(bt_strategy: Any, live_strategy: Any) -> bool:
    bt_text = str(bt_strategy or "").strip()
    live_text = str(live_strategy or "").strip()
    if not bt_text and not live_text:
        return False
    return bt_text != live_text


def _resolve_tail_force_exit_ts(backtest_signals: List[Dict[str, Any]]) -> Optional[datetime]:
    latest: Optional[datetime] = None
    for item in backtest_signals:
        side = str(item.get("side") or "").strip().lower()
        exit_reason = str(item.get("exit_reason") or "").strip().lower()
        if side != "exit" or exit_reason != "force_exit":
            continue
        dt = _parse_iso_dt(item.get("signal_ts"))
        if dt is None:
            continue
        if latest is None or dt > latest:
            latest = dt
    return latest


def _is_tail_force_exit_only_in_backtest(bt: Dict[str, Any], tail_force_exit_ts: Optional[datetime]) -> bool:
    side = str(bt.get("side") or "").strip().lower()
    exit_reason = str(bt.get("exit_reason") or "").strip().lower()
    if side != "exit" or exit_reason != "force_exit" or tail_force_exit_ts is None:
        return False
    bt_dt = _parse_iso_dt(bt.get("signal_ts"))
    if bt_dt is None:
        return False
    # 以秒為單位比對，避免毫秒誤差。
    return int(bt_dt.timestamp()) == int(tail_force_exit_ts.timestamp())


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
    tail_force_exit_ts = _resolve_tail_force_exit_ts(backtest_signals)

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
                if _is_tail_force_exit_only_in_backtest(bt, tail_force_exit_ts):
                    rows.append(
                        {
                            "pair": pair,
                            "side": side,
                            "bucket_ts": bucket_ts,
                            "signal_lamp": "blue",
                            "fill_lamp": "blue",
                            "signal_state": IGNORED_TAIL_FORCE_EXIT,
                            "price_state": "IGNORED",
                            "qty_state": "IGNORED",
                            "bt_signal_ts": bt.get("signal_ts", ""),
                            "live_signal_ts": "",
                            "bt_price": bt.get("price"),
                            "live_price": None,
                            "price_diff_bps": None,
                            "bt_amount": bt.get("amount"),
                            "live_amount": None,
                            "qty_diff_ratio": None,
                            "reason": "回測尾端 force_exit（區間收尾平倉），Live 無對應訊號；此列不納入 mismatch 統計",
                        }
                    )
                    continue
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

            bt_signal_ts = str(bt.get("signal_ts", ""))
            live_signal_ts = str(lv.get("signal_ts", ""))
            time_is_same = _is_same_second(bt_signal_ts, live_signal_ts)
            strategy_mismatch = _is_strategy_mismatch(bt.get("strategy"), lv.get("strategy"))

            fill_lamp = "green" if (price_state == "MATCH" and qty_state == "MATCH") else "yellow"
            if fill_lamp == "green" and time_is_same and strategy_mismatch:
                reason = "策略部一致"
            else:
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
                    "bt_signal_ts": bt_signal_ts,
                    "live_signal_ts": live_signal_ts,
                    "bt_price": bt_price,
                    "live_price": lv_price,
                    "price_diff_bps": p_diff,
                    "bt_amount": bt_amount,
                    "live_amount": lv_amount,
                    "qty_diff_ratio": q_diff,
                    "reason": reason,
                }
            )

    rows.sort(
        key=lambda item: (
            str(item.get("bt_signal_ts") or item.get("live_signal_ts") or item.get("bucket_ts") or ""),
            str(item.get("pair") or ""),
            str(item.get("side") or ""),
            str(item.get("bucket_ts") or ""),
            str(item.get("bt_signal_ts") or ""),
            str(item.get("live_signal_ts") or ""),
        )
    )
    return rows
