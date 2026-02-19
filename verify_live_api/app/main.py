"""verify_live API 入口。"""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config_compare_service import compare_profile_vs_live_config
from .config_loader import scan_configs
from .db import (
    get_compare_details,
    get_compare_summary,
    get_data_job,
    delete_profile,
    get_job,
    request_cancel_job,
    get_profile,
    get_signals,
    init_db,
    list_jobs,
    list_profiles,
    save_profile,
)
from .data_job_service import start_data_job
from .job_service import start_job
from .schemas import JobCreateRequest, SaveProfileRequest
from .settings import DB_PATH, DEFAULT_PRICE_TOL_BPS, DEFAULT_QTY_TOL_RATIO


def _profile_row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    payload = {}
    try:
        payload = json.loads(row.get("payload_json", "{}"))
    except Exception:
        payload = {}
    return {
        "profile_id": row.get("profile_id", ""),
        "profile_name": row.get("profile_name", ""),
        "payload": payload,
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _tail_lines(path: Path, lines: int) -> List[str]:
    if not path.exists():
        return []
    dq: deque[str] = deque(maxlen=lines)
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            dq.append(line.rstrip("\r\n"))
    return list(dq)


app = FastAPI(title="verify_live API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5179",
        "http://localhost:5179",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    # 允許本機 localhost/127.0.0.1 任意埠（例如你自訂 15179）。
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/verify/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "db_path": str(DB_PATH), "db_exists": DB_PATH.exists()}


@app.get("/api/verify/defaults")
def defaults() -> Dict[str, Any]:
    return {
        "live_api_base_url": os.getenv("VERIFY_LIVE_API_BASE_URL", ""),
        "live_api_username": os.getenv("VERIFY_LIVE_API_USER", ""),
        "live_api_password": os.getenv("VERIFY_LIVE_API_PASSWORD", ""),
        "price_tolerance_bps": DEFAULT_PRICE_TOL_BPS,
        "qty_tolerance_ratio": DEFAULT_QTY_TOL_RATIO,
    }


@app.get("/api/verify/configs")
def get_configs() -> Dict[str, List[Dict[str, Any]]]:
    return {"items": scan_configs()}


@app.get("/api/verify/configs/{config_id}")
def get_config(config_id: str) -> Dict[str, Any]:
    items = scan_configs()
    for item in items:
        if item["config_id"] == config_id:
            return item
    raise HTTPException(status_code=404, detail="找不到 config_id")


@app.get("/api/verify/profiles")
def api_list_profiles() -> Dict[str, List[Dict[str, Any]]]:
    rows = list_profiles()
    return {"items": [_profile_row_to_dict(r) for r in rows]}


@app.get("/api/verify/profiles/{profile_id}")
def api_get_profile(profile_id: str) -> Dict[str, Any]:
    row = get_profile(profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 profile_id")
    return _profile_row_to_dict(row)


@app.post("/api/verify/profiles/{profile_id}/config-compare")
def api_profile_config_compare(profile_id: str) -> Dict[str, Any]:
    try:
        return compare_profile_vs_live_config(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/verify/profiles")
def api_save_profile(req: SaveProfileRequest) -> Dict[str, Any]:
    payload_dict = req.payload.model_dump()
    row = save_profile(req.profile_id, payload_dict)
    return _profile_row_to_dict(row)


@app.delete("/api/verify/profiles/{profile_id}")
def api_delete_profile(profile_id: str) -> Dict[str, Any]:
    ok = delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="找不到 profile_id")
    return {"ok": True, "profile_id": profile_id}


@app.get("/api/verify/jobs")
def api_list_jobs(limit: int = Query(default=50, ge=1, le=500)) -> Dict[str, Any]:
    return {"items": list_jobs(limit=limit)}


@app.post("/api/verify/jobs")
def api_create_job(req: JobCreateRequest) -> Dict[str, Any]:
    row = start_job(req.profile_id)
    return row


@app.get("/api/verify/jobs/{job_id}")
def api_get_job(job_id: str) -> Dict[str, Any]:
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 job_id")
    return row


@app.get("/api/verify/jobs/{job_id}/logs/tail")
def api_get_job_logs_tail(
    job_id: str,
    lines: int = Query(default=30, ge=1, le=300),
) -> Dict[str, Any]:
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 job_id")
    run_dir = str(row.get("run_dir") or "").strip()
    log_path = (Path(run_dir) / "backtest.log") if run_dir else Path("")
    tail = _tail_lines(log_path, lines) if run_dir else []
    return {
        "job_id": job_id,
        "log_path": str(log_path) if run_dir else "",
        "lines": tail,
        "text": "\n".join(tail),
    }


@app.post("/api/verify/data-jobs")
def api_create_data_job(req: JobCreateRequest) -> Dict[str, Any]:
    return start_data_job(req.profile_id)


@app.get("/api/verify/data-jobs/{data_job_id}")
def api_get_data_job(data_job_id: str) -> Dict[str, Any]:
    row = get_data_job(data_job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 data_job_id")
    return row


@app.get("/api/verify/data-jobs/{data_job_id}/logs/tail")
def api_get_data_job_logs_tail(
    data_job_id: str,
    lines: int = Query(default=30, ge=1, le=300),
) -> Dict[str, Any]:
    row = get_data_job(data_job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 data_job_id")
    run_dir = str(row.get("run_dir") or "").strip()
    log_path = (Path(run_dir) / "download_data.log") if run_dir else Path("")
    tail = _tail_lines(log_path, lines) if run_dir else []
    return {
        "data_job_id": data_job_id,
        "log_path": str(log_path) if run_dir else "",
        "lines": tail,
        "text": "\n".join(tail),
    }


@app.post("/api/verify/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str) -> Dict[str, Any]:
    row = request_cancel_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 job_id")
    return row


@app.get("/api/verify/jobs/{job_id}/signals")
def api_get_signals(
    job_id: str,
    source: str = Query(..., pattern="^(backtest|live)$"),
    limit: int = Query(default=5000, ge=1, le=20000),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 job_id")
    return {"job_id": job_id, "source": source, "items": get_signals(job_id, source, limit, offset)}


@app.get("/api/verify/jobs/{job_id}/compare/summary")
def api_compare_summary(job_id: str) -> Dict[str, Any]:
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 job_id")
    summary = get_compare_summary(job_id)
    summary["job_id"] = job_id
    return summary


@app.get("/api/verify/jobs/{job_id}/compare/details")
def api_compare_details(
    job_id: str,
    limit: int = Query(default=2000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    row = get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="找不到 job_id")
    return {"job_id": job_id, "items": get_compare_details(job_id, limit, offset)}
