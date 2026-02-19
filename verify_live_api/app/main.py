"""verify_live API 入口。"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config_loader import scan_configs
from .db import (
    get_compare_details,
    get_compare_summary,
    get_job,
    get_profile,
    get_signals,
    init_db,
    list_jobs,
    list_profiles,
    save_profile,
)
from .job_service import start_job
from .schemas import JobCreateRequest, SaveProfileRequest
from .settings import DB_PATH


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


@app.post("/api/verify/profiles")
def api_save_profile(req: SaveProfileRequest) -> Dict[str, Any]:
    payload_dict = req.payload.model_dump()
    row = save_profile(req.profile_id, payload_dict)
    return _profile_row_to_dict(row)


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
