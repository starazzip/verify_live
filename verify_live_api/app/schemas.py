"""Pydantic 資料模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from . import settings


class ConfigItem(BaseModel):
    config_id: str
    config_path: str
    label: str
    strategy: str = ""
    strategy_path: str = ""
    timeframe: str = "5m"
    fee: Optional[float] = None
    datadir: str = ""


class VerifyProfilePayload(BaseModel):
    profile_name: str = Field(min_length=1, max_length=120)
    config_path: str = Field(min_length=1)
    strategy: str = Field(min_length=1)
    strategy_path: str = "user_data/strategies"
    timeframe: str = "5m"
    timerange_start: str = Field(min_length=8)
    timerange_end_mode: Literal["fixed", "now"] = "now"
    timerange_end_fixed: Optional[str] = None
    fee: Optional[float] = None
    datadir: str = ""
    live_api_base_url: str = ""
    live_api_username: str = ""
    live_api_password_env: str = "VERIFY_LIVE_API_PASSWORD"
    live_strategy_name: Optional[str] = None
    price_tolerance_bps: float = settings.DEFAULT_PRICE_TOL_BPS
    qty_tolerance_ratio: float = settings.DEFAULT_QTY_TOL_RATIO

    @field_validator("timerange_end_fixed")
    @classmethod
    def _check_fixed_end(cls, value: Optional[str], info):  # type: ignore[override]
        mode = info.data.get("timerange_end_mode")
        if mode == "fixed" and not value:
            raise ValueError("timerange_end_mode=fixed 時必須提供 timerange_end_fixed")
        return value

    @field_validator("price_tolerance_bps")
    @classmethod
    def _check_price_tol(cls, value: float) -> float:
        if value < 0:
            raise ValueError("price_tolerance_bps 不可小於 0")
        return value

    @field_validator("qty_tolerance_ratio")
    @classmethod
    def _check_qty_tol(cls, value: float) -> float:
        if value < 0:
            raise ValueError("qty_tolerance_ratio 不可小於 0")
        return value


class VerifyProfileRecord(BaseModel):
    profile_id: str
    payload: VerifyProfilePayload
    created_at: datetime
    updated_at: datetime


class SaveProfileRequest(BaseModel):
    profile_id: Optional[str] = None
    payload: VerifyProfilePayload


class JobCreateRequest(BaseModel):
    profile_id: str


class VerifyJobRecord(BaseModel):
    job_id: str
    profile_id: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: str = ""
    resolved_timerange_start: str = ""
    resolved_timerange_end: str = ""
    run_dir: str = ""
    backtest_exit_code: Optional[int] = None


class SignalRecord(BaseModel):
    source: Literal["backtest", "live"]
    pair: str
    side: Literal["entry", "exit"]
    bucket_ts: str
    signal_ts: str
    price: Optional[float] = None
    amount: Optional[float] = None
    enter_tag: str = ""
    exit_reason: str = ""
    trade_id: str = ""
    strategy: str = ""


class CompareSummary(BaseModel):
    total_rows: int
    signal_green: int
    signal_red: int
    fill_green: int
    fill_yellow: int
    fill_red: int
    signal_match_rate: float
    fill_green_rate: float

