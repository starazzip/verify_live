"""Freqtrade REST API Client。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from . import settings


class FreqtradeApiError(RuntimeError):
    """Freqtrade API 錯誤。"""


@dataclass
class FreqtradeCredentials:
    base_url: str
    username: str
    password: str


class FreqtradeApiClient:
    def __init__(self, creds: FreqtradeCredentials, timeout: int = settings.REQUEST_TIMEOUT_SEC):
        self.creds = creds
        self.timeout = timeout
        self._token: Optional[str] = None

    @property
    def _api_base(self) -> str:
        return self.creds.base_url.rstrip("/")

    def login(self) -> str:
        url = f"{self._api_base}/api/v1/token/login"
        payload = {"username": self.creds.username, "password": self.creds.password}
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
        except Exception as exc:
            raise FreqtradeApiError(f"連線失敗：{exc}") from exc
        if resp.status_code >= 400:
            raise FreqtradeApiError(f"登入失敗（HTTP {resp.status_code}）：{resp.text[:300]}")
        data = resp.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            raise FreqtradeApiError("登入成功但回應缺少 access_token")
        self._token = str(token)
        return self._token

    def _headers(self) -> Dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self._api_base}{path}"
        headers = self._headers()
        resp = requests.get(url, headers=headers, params=params or {}, timeout=self.timeout)
        if resp.status_code == 401:
            self.login()
            headers = self._headers()
            resp = requests.get(url, headers=headers, params=params or {}, timeout=self.timeout)
        if resp.status_code >= 400:
            raise FreqtradeApiError(f"GET {path} 失敗（HTTP {resp.status_code}）：{resp.text[:300]}")
        return resp.json()

    def fetch_all_trades(self, limit: int = 500) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        offset = 0
        while True:
            payload = self._get("/api/v1/trades", params={"limit": limit, "offset": offset})
            if isinstance(payload, dict):
                items = payload.get("trades") if isinstance(payload.get("trades"), list) else payload.get("data")
                if items is None and isinstance(payload.get("items"), list):
                    items = payload["items"]
                if not isinstance(items, list):
                    items = []
            elif isinstance(payload, list):
                items = payload
            else:
                items = []

            all_items.extend(items)
            if len(items) < limit:
                break
            offset += limit
        return all_items

    def fetch_open_trades(self) -> List[Dict[str, Any]]:
        payload = self._get("/api/v1/status")
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("status"), list):
                return payload["status"]
            if isinstance(payload.get("data"), list):
                return payload["data"]
        return []

