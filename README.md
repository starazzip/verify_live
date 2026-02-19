# verify_live（獨立專案）

用於驗證 Spot 實盤與回測訊號一致性。

## 預設目錄佈局（建議）
`verify_live` 預設假設與 Freqtrade 的 `user_data` 同層：

```text
<你的專案根目錄>/
  user_data/
  verify_live/
```

若照此佈局，`config_path / strategy_path / datadir` 可直接使用 `user_data/...` 相對路徑。

## 功能
1. Web 選 config，自動帶入策略/週期/資料路徑，允許手動調整。
2. 啟動後會自動從 `.env` 帶入 Live API 連線欄位（`base_url / username / password`）。
3. 密碼欄位預設脫敏，可透過「顯示 / 隱藏」按鈕暫時查看。
4. Profile 可儲存、載入、刪除（刪除時會連同相關 job 結果）。
5. 一鍵「回測驗證」：執行完整指定區間回測（不依交易紀錄截斷）。
6. 透過 Freqtrade REST API 讀取 live 交易，做同根 K 比對。
7. 雙燈號顯示：
   - 訊號燈：同根 K 是否一致
   - 成交燈：價量是否在容忍度內
8. 可按「更新 K 線」：依目前 config / timeframe / 日期區間，向交易所下載資料。
9. 任務執行中可按「停止驗證」中止回測任務。
10. 回測與更新 K 線執行中，頁面會即時顯示 Freqtrade 最後幾行輸出。
11. 可按「比對 Live Config」檢查本地 config 與 Freqtrade `show_config` 是否一致。
12. Config 比對含幣對白名單/黑名單（透過 Live API `whitelist` / `blacklist`）差異檢查。

## 目錄
- `verify_live_api/`: FastAPI 後端
- `verify_live_web/`: React + Vite 前端
- `data/verify_live.db`: Profile / Job / Signals / Compare 資料庫
- `profiles/`: 可選 profile 檔案資料夾（保留）
- `scripts/`: 啟動腳本

## 安裝

### 1) 建立後端 venv（Windows / Linux 共用）
```bash
cd verify_live
python -m venv verify_live_api/.venv
```

### 2) 安裝後端依賴
Windows:
```powershell
verify_live_api\.venv\Scripts\python -m pip install -r verify_live_api\requirements.txt
```
Linux:
```bash
verify_live_api/.venv/bin/python -m pip install -r verify_live_api/requirements.txt
```

### 3) 安裝前端依賴（Windows / Linux 共用）
```bash
cd verify_live
npm --prefix verify_live_web install
```

### 4) 建立環境變數檔
Windows:
```powershell
Copy-Item .env.example .env
```
Linux:
```bash
cp .env.example .env
```
再編輯 `.env`，至少填入：
- `VERIFY_LIVE_API_BASE_URL`
- `VERIFY_LIVE_API_USER`
- `VERIFY_LIVE_API_PASSWORD`

## 啟動（跨平台）

### 一鍵啟動（建議，Windows / Linux 同指令）
```bash
cd verify_live
python scripts/start_verify_live.py
```
預設會自動讀取 `verify_live/.env` 的：
- `VERIFY_LIVE_API_HOST`
- `VERIFY_LIVE_API_PORT`
- `VERIFY_LIVE_WEB_PORT`
若 API 埠已被占用：
- 若該埠是既有 verify_live API，啟動器會自動沿用，不會重啟 API。
- 若是其他程式占用，會直接報錯提醒你更換埠號或釋放埠。

若你懷疑埠上是舊版 API（例如更新後 `config` 清單仍為空），可強制重啟：
```bash
cd verify_live
python scripts/start_verify_live.py --restart-api
```

### 終止程序
- 預設可用 `Ctrl+C` 停止（會自動關閉 API / Web 子程序樹）。
- 若仍殘留程序，可手動執行：
Windows:
```powershell
taskkill /F /T /IM node.exe
taskkill /F /T /IM uvicorn.exe
```
Linux:
```bash
pkill -f "vite"
pkill -f "uvicorn app.main:app"
```

### 分開啟動（Windows / Linux 同指令）
API:
```bash
cd verify_live
python scripts/start_verify_live_api.py
```
Web:
```bash
cd verify_live
python scripts/start_verify_live_web.py --api-base http://127.0.0.1:8011
```

## PowerShell 腳本（Windows 可選）
若你偏好 PowerShell，也可使用：
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_verify_live.ps1
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
4. 路徑統一解析規則（`config_path / strategy_path / datadir`）：
   - 絕對路徑：直接使用
   - 相對路徑：依序嘗試
     1) `VERIFY_LIVE_WORKSPACE_ROOT`
     2) `verify_live` 上層目錄
     3) `verify_live` 專案目錄
   - `strategy` 類別若不在填寫的 `strategy_path`，會自動在 `user_data` 下各層 `strategies` 目錄補找
5. 若你的實際資料不在預設佈局，可在 `.env` 設定：
   - `VERIFY_LIVE_WORKSPACE_ROOT=<你的交易專案根目錄>`
6. `VERIFY_LIVE_CONFIG_ROOTS` 若使用相對路徑，也會套用上述同一套解析規則。

## API 摘要
- `GET /api/verify/defaults`
- `GET /api/verify/configs`
- `GET /api/verify/profiles`
- `POST /api/verify/profiles`
- `POST /api/verify/profiles/{profile_id}/config-compare`
- `DELETE /api/verify/profiles/{profile_id}`
- `POST /api/verify/jobs`
- `GET /api/verify/jobs/{job_id}`
- `GET /api/verify/jobs/{job_id}/logs/tail`
- `POST /api/verify/jobs/{job_id}/cancel`
- `POST /api/verify/data-jobs`
- `GET /api/verify/data-jobs/{data_job_id}`
- `GET /api/verify/data-jobs/{data_job_id}/logs/tail`
- `GET /api/verify/jobs/{job_id}/signals?source=backtest|live`
- `GET /api/verify/jobs/{job_id}/compare/summary`
- `GET /api/verify/jobs/{job_id}/compare/details`
