# verify_live（獨立專案）

用於驗證 Spot 實盤與回測訊號一致性。

## 功能
1. Web 選 config，自動帶入策略/週期/資料路徑，允許手動調整。
2. 一鍵「回測驗證」：執行完整指定區間回測（不依交易紀錄截斷）。
3. 透過 Freqtrade REST API 讀取 live 交易，做同根 K 比對。
4. 雙燈號顯示：
   - 訊號燈：同根 K 是否一致
   - 成交燈：價量是否在容忍度內

## 目錄
- `verify_live_api/`: FastAPI 後端
- `verify_live_web/`: React + Vite 前端
- `data/verify_live.db`: Profile / Job / Signals / Compare 資料庫
- `profiles/`: 可選 profile 檔案資料夾（保留）
- `scripts/`: 啟動腳本

## 安裝

### 1) 後端
```powershell
cd verify_live/verify_live_api
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements.txt
```

### 2) 前端
```powershell
cd verify_live/verify_live_web
npm install
```

### 3) 環境變數
```powershell
cd verify_live
Copy-Item .env.example .env
```
再編輯 `.env`，至少填入：
- `VERIFY_LIVE_API_BASE_URL`
- `VERIFY_LIVE_API_USER`
- `VERIFY_LIVE_API_PASSWORD`

## 啟動

### 一鍵啟動（建議）
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_verify_live.ps1
```

### 分開啟動
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_verify_live_api.ps1
powershell -ExecutionPolicy Bypass -File scripts/start_verify_live_web.ps1
```

預設：
- API: `http://127.0.0.1:8011`
- Web: `http://127.0.0.1:5179`

## 重要設定
1. `timerange_end_mode=now` 會在任務啟動時解析為當下 UTC 日期。
2. 目前只做 Spot。
3. 第一版預設容忍度：
   - 價格：10 bps
   - 數量：0.5%（`qty_tolerance_ratio=0.005`）
4. 若 config / strategy / datadir 不在本專案目錄下，可在 `.env` 設定：
   - `VERIFY_LIVE_WORKSPACE_ROOT=<你的交易專案根目錄>`

## API 摘要
- `GET /api/verify/configs`
- `GET /api/verify/profiles`
- `POST /api/verify/profiles`
- `POST /api/verify/jobs`
- `GET /api/verify/jobs/{job_id}`
- `GET /api/verify/jobs/{job_id}/signals?source=backtest|live`
- `GET /api/verify/jobs/{job_id}/compare/summary`
- `GET /api/verify/jobs/{job_id}/compare/details`
