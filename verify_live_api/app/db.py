"""SQLite 存取層。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import settings


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                profile_id TEXT PRIMARY KEY,
                profile_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error TEXT DEFAULT '',
                resolved_timerange_start TEXT DEFAULT '',
                resolved_timerange_end TEXT DEFAULT '',
                run_dir TEXT DEFAULT '',
                backtest_exit_code INTEGER,
                FOREIGN KEY(profile_id) REFERENCES profiles(profile_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                job_id TEXT NOT NULL,
                source TEXT NOT NULL,
                seq_no INTEGER NOT NULL,
                pair TEXT NOT NULL,
                side TEXT NOT NULL,
                bucket_ts TEXT NOT NULL,
                signal_ts TEXT NOT NULL,
                price REAL,
                amount REAL,
                enter_tag TEXT DEFAULT '',
                exit_reason TEXT DEFAULT '',
                trade_id TEXT DEFAULT '',
                strategy TEXT DEFAULT '',
                raw_payload_json TEXT DEFAULT '',
                PRIMARY KEY(job_id, source, seq_no),
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS compare_results (
                job_id TEXT NOT NULL,
                seq_no INTEGER NOT NULL,
                pair TEXT NOT NULL,
                side TEXT NOT NULL,
                bucket_ts TEXT NOT NULL,
                signal_lamp TEXT NOT NULL,
                fill_lamp TEXT NOT NULL,
                signal_state TEXT NOT NULL,
                price_state TEXT NOT NULL,
                qty_state TEXT NOT NULL,
                bt_signal_ts TEXT DEFAULT '',
                live_signal_ts TEXT DEFAULT '',
                bt_price REAL,
                live_price REAL,
                price_diff_bps REAL,
                bt_amount REAL,
                live_amount REAL,
                qty_diff_ratio REAL,
                reason TEXT DEFAULT '',
                PRIMARY KEY(job_id, seq_no),
                FOREIGN KEY(job_id) REFERENCES jobs(job_id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_signals_job_source ON signals(job_id, source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_compare_job ON compare_results(job_id)")
        conn.commit()


def list_profiles() -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT profile_id, profile_name, payload_json, created_at, updated_at
            FROM profiles
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def get_profile(profile_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT profile_id, profile_name, payload_json, created_at, updated_at
            FROM profiles
            WHERE profile_id = ?
            """,
            (profile_id,),
        ).fetchone()
    return dict(row) if row else None


def save_profile(profile_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    now = utc_now_iso()
    pid = profile_id or f"pf_{uuid.uuid4().hex[:12]}"
    payload_json = json.dumps(payload, ensure_ascii=False)
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM profiles WHERE profile_id=?", (pid,)).fetchone() is not None
        if exists:
            conn.execute(
                """
                UPDATE profiles
                SET profile_name=?, payload_json=?, updated_at=?
                WHERE profile_id=?
                """,
                (payload.get("profile_name", ""), payload_json, now, pid),
            )
        else:
            conn.execute(
                """
                INSERT INTO profiles(profile_id, profile_name, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pid, payload.get("profile_name", ""), payload_json, now, now),
            )
        conn.commit()
    row = get_profile(pid)
    if row is None:
        raise RuntimeError("保存 profile 失敗")
    return row


def create_job(profile_id: str, run_dir: Path) -> Dict[str, Any]:
    now = utc_now_iso()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs(job_id, profile_id, status, created_at, run_dir)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (job_id, profile_id, now, str(run_dir)),
        )
        conn.commit()
    row = get_job(job_id)
    if row is None:
        raise RuntimeError("建立 job 失敗")
    return row


def update_job(job_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    cols = []
    vals: List[Any] = []
    for k, v in kwargs.items():
        cols.append(f"{k}=?")
        vals.append(v)
    vals.append(job_id)
    sql = f"UPDATE jobs SET {', '.join(cols)} WHERE job_id=?"
    with connect() as conn:
        conn.execute(sql, vals)
        conn.commit()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def replace_signals(job_id: str, source: str, rows: Iterable[Dict[str, Any]]) -> int:
    entries = list(rows)
    with connect() as conn:
        conn.execute("DELETE FROM signals WHERE job_id=? AND source=?", (job_id, source))
        if entries:
            payload = [
                (
                    job_id,
                    source,
                    idx,
                    str(item.get("pair", "")),
                    str(item.get("side", "")),
                    str(item.get("bucket_ts", "")),
                    str(item.get("signal_ts", "")),
                    item.get("price"),
                    item.get("amount"),
                    str(item.get("enter_tag", "")),
                    str(item.get("exit_reason", "")),
                    str(item.get("trade_id", "")),
                    str(item.get("strategy", "")),
                    json.dumps(item.get("raw_payload", {}), ensure_ascii=False),
                )
                for idx, item in enumerate(entries, start=1)
            ]
            conn.executemany(
                """
                INSERT INTO signals(
                    job_id, source, seq_no, pair, side, bucket_ts, signal_ts,
                    price, amount, enter_tag, exit_reason, trade_id, strategy, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
        conn.commit()
    return len(entries)


def get_signals(job_id: str, source: str, limit: int = 5000, offset: int = 0) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT source, pair, side, bucket_ts, signal_ts, price, amount, enter_tag, exit_reason, trade_id, strategy
            FROM signals
            WHERE job_id=? AND source=?
            ORDER BY seq_no
            LIMIT ? OFFSET ?
            """,
            (job_id, source, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def replace_compare_results(job_id: str, rows: Iterable[Dict[str, Any]]) -> int:
    entries = list(rows)
    with connect() as conn:
        conn.execute("DELETE FROM compare_results WHERE job_id=?", (job_id,))
        if entries:
            payload = [
                (
                    job_id,
                    idx,
                    str(item.get("pair", "")),
                    str(item.get("side", "")),
                    str(item.get("bucket_ts", "")),
                    str(item.get("signal_lamp", "red")),
                    str(item.get("fill_lamp", "red")),
                    str(item.get("signal_state", "")),
                    str(item.get("price_state", "")),
                    str(item.get("qty_state", "")),
                    str(item.get("bt_signal_ts", "")),
                    str(item.get("live_signal_ts", "")),
                    item.get("bt_price"),
                    item.get("live_price"),
                    item.get("price_diff_bps"),
                    item.get("bt_amount"),
                    item.get("live_amount"),
                    item.get("qty_diff_ratio"),
                    str(item.get("reason", "")),
                )
                for idx, item in enumerate(entries, start=1)
            ]
            conn.executemany(
                """
                INSERT INTO compare_results(
                    job_id, seq_no, pair, side, bucket_ts, signal_lamp, fill_lamp,
                    signal_state, price_state, qty_state, bt_signal_ts, live_signal_ts,
                    bt_price, live_price, price_diff_bps, bt_amount, live_amount,
                    qty_diff_ratio, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
        conn.commit()
    return len(entries)


def get_compare_details(job_id: str, limit: int = 2000, offset: int = 0) -> List[Dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT pair, side, bucket_ts, signal_lamp, fill_lamp, signal_state, price_state, qty_state,
                   bt_signal_ts, live_signal_ts, bt_price, live_price, price_diff_bps,
                   bt_amount, live_amount, qty_diff_ratio, reason
            FROM compare_results
            WHERE job_id=?
            ORDER BY seq_no
            LIMIT ? OFFSET ?
            """,
            (job_id, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_compare_summary(job_id: str) -> Dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                SUM(CASE WHEN signal_lamp='green' THEN 1 ELSE 0 END) AS signal_green,
                SUM(CASE WHEN signal_lamp='red' THEN 1 ELSE 0 END) AS signal_red,
                SUM(CASE WHEN fill_lamp='green' THEN 1 ELSE 0 END) AS fill_green,
                SUM(CASE WHEN fill_lamp='yellow' THEN 1 ELSE 0 END) AS fill_yellow,
                SUM(CASE WHEN fill_lamp='red' THEN 1 ELSE 0 END) AS fill_red
            FROM compare_results
            WHERE job_id=?
            """,
            (job_id,),
        ).fetchone()
    data = dict(row) if row else {}
    total = int(data.get("total_rows") or 0)
    signal_green = int(data.get("signal_green") or 0)
    fill_green = int(data.get("fill_green") or 0)
    data["signal_match_rate"] = (signal_green / total) if total else 0.0
    data["fill_green_rate"] = (fill_green / total) if total else 0.0
    return data

