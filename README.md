# verify_live (Standalone Project)

This project validates signal consistency between live trading and backtesting in Freqtrade, supporting both Spot and Futures.

## Project Goal
- Provide a reproducible verification workflow to reduce investigation cost when live and backtest results diverge.
- Use profiles to manage parameters for repeatable runs and easier comparison.
- Use lamp indicators and detailed rows to locate mismatches (signal, price, quantity).

## Key Features
1. Select config from Web UI and auto-fill strategy, timeframe, and data path.
2. Profiles can be saved, loaded, and deleted.
3. Run backtest verification and compare against live API signals.
4. Dual lamps:
   - Signal lamp: same candle bucket match
   - Fill lamp: price/quantity tolerance match
5. Update candle data and monitor job logs in real time.
6. Compare local config with Live `show_config` (including whitelist/blacklist differences).

## Recommended Layout
```text
<workspace-root>/
  user_data/
  verify_live/
```

With this layout, `config_path / strategy_path / datadir` can directly use `user_data/...` relative paths.

## Project Structure
- `verify_live_api/`: Backend service (FastAPI)
- `verify_live_web/`: Frontend app (React + Vite)
- `data/verify_live.db`: SQLite database for profiles/jobs/signals/comparisons
- `profiles/`: Reserved folder
- `scripts/`: Startup and helper scripts

## Windows Setup & Run

### 1) Create backend virtual environment
```powershell
cd verify_live
python -m venv verify_live_api\.venv
```

### 2) Install backend dependencies
```powershell
verify_live_api\.venv\Scripts\python -m pip install -r verify_live_api\requirements.txt
```

### 3) Install frontend dependencies
```powershell
npm --prefix verify_live_web install
```

### 4) Create environment file
```powershell
Copy-Item .env.example .env
```
Required fields:
- `VERIFY_LIVE_API_BASE_URL`
- `VERIFY_LIVE_API_USER`
- `VERIFY_LIVE_API_PASSWORD`

### 5) Start all services (recommended)
```powershell
python scripts\start_verify_live.py
```

### 6) Force restart API (if needed)
```powershell
python scripts\start_verify_live.py --restart-api
```

### 7) Start services separately (optional)
API:
```powershell
python scripts\start_verify_live_api.py
```
Web:
```powershell
python scripts\start_verify_live_web.py --api-base http://127.0.0.1:8011
```

### 8) Stop services
- Press `Ctrl+C` in the launcher terminal.
- If processes remain:
```powershell
taskkill /F /T /IM node.exe
taskkill /F /T /IM uvicorn.exe
```

### 9) Windows PowerShell script (optional)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_verify_live.ps1
```

## Linux Setup & Run

### 1) Create backend virtual environment
```bash
cd verify_live
python -m venv verify_live_api/.venv
```

### 2) Install backend dependencies
```bash
verify_live_api/.venv/bin/python -m pip install -r verify_live_api/requirements.txt
```

### 3) Install frontend dependencies
```bash
npm --prefix verify_live_web install
```

### 4) Create environment file
```bash
cp .env.example .env
```
Required fields:
- `VERIFY_LIVE_API_BASE_URL`
- `VERIFY_LIVE_API_USER`
- `VERIFY_LIVE_API_PASSWORD`

### 5) Start all services (recommended)
```bash
python scripts/start_verify_live.py
```

### 6) Force restart API (if needed)
```bash
python scripts/start_verify_live.py --restart-api
```

### 7) Start services separately (optional)
API:
```bash
python scripts/start_verify_live_api.py
```
Web:
```bash
python scripts/start_verify_live_web.py --api-base http://127.0.0.1:8011
```

### 8) Stop services
- Press `Ctrl+C` in the launcher terminal.
- If processes remain:
```bash
pkill -f "vite"
pkill -f "uvicorn app.main:app"
```

## Default Ports
- API: `http://127.0.0.1:8011`
- Web: `http://127.0.0.1:5179`

## Important Notes
1. `timerange_end_mode=now` is resolved to current UTC date at runtime.
2. Spot and Futures are both supported; actual behavior depends on `trading_mode`, `margin_mode`, exchange settings, and strategy `can_short`.
3. Default tolerance: price `10 bps`, quantity `0.5%` (`qty_tolerance_ratio=0.005`).
4. Path resolution for `config_path / strategy_path / datadir`:
   - Absolute path: used directly.
   - Relative path: resolved in order:
     1) `VERIFY_LIVE_WORKSPACE_ROOT`
     2) Parent directory of `verify_live`
     3) `verify_live` project root
5. If strategy class is not found in `strategy_path`, the system searches `user_data/**/strategies`.
6. Relative paths in `VERIFY_LIVE_CONFIG_ROOTS` follow the same resolution rules.

## Recommended Verification Flow
1. Load or create a profile.
2. Run "Compare Live Config" first to confirm key parameters.
3. Run "Update Candles" when data refresh is needed.
4. Run "Backtest Verification" and inspect summary/details.

## API Summary
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

## Security Notes
- `.env` may contain credentials/API keys and must not be committed.
- Keep only placeholder keys in `.env.example`, never real secrets.

---

# verify_live（獨立專案）

本專案用於驗證 Freqtrade 實盤與回測訊號的一致性，支援 Spot 與 Futures。

## 專案目標
- 建立可重現的驗證流程，降低「實盤與回測不一致」的排查成本。
- 以 Profile 管理參數，支援重複執行與結果比對。
- 透過燈號與明細快速定位差異（訊號、價格、數量）。

## 核心功能
1. 以 Web 介面選擇 config，並自動帶入策略、週期、資料路徑。
2. Profile 可儲存、載入、刪除。
3. 一鍵執行回測驗證，並與 Live API 訊號比對。
4. 提供雙燈號：
   - 訊號燈：同根 K 是否一致
   - 成交燈：價量是否在容忍度內
5. 可更新 K 線資料並即時追蹤任務日誌。
6. 支援比對本地 config 與 Live `show_config`（含白名單/黑名單差異）。

## 建議目錄佈局
```text
<workspace-root>/
  user_data/
  verify_live/
```

若使用此佈局，`config_path / strategy_path / datadir` 可直接使用 `user_data/...` 相對路徑。

## 專案目錄
- `verify_live_api/`: 後端服務（FastAPI）
- `verify_live_web/`: 前端應用（React + Vite）
- `data/verify_live.db`: Profile / Job / Signals / Compare 的 SQLite 資料庫
- `profiles/`: 預留資料夾
- `scripts/`: 啟動與管理腳本

## Windows 安裝與啟動

### 1) 建立後端虛擬環境
```powershell
cd verify_live
python -m venv verify_live_api\.venv
```

### 2) 安裝後端依賴
```powershell
verify_live_api\.venv\Scripts\python -m pip install -r verify_live_api\requirements.txt
```

### 3) 安裝前端依賴
```powershell
npm --prefix verify_live_web install
```

### 4) 建立環境變數檔
```powershell
Copy-Item .env.example .env
```
必填欄位：
- `VERIFY_LIVE_API_BASE_URL`
- `VERIFY_LIVE_API_USER`
- `VERIFY_LIVE_API_PASSWORD`

### 5) 一鍵啟動（建議）
```powershell
python scripts\start_verify_live.py
```

### 6) 強制重啟 API（必要時）
```powershell
python scripts\start_verify_live.py --restart-api
```

### 7) 分開啟動（可選）
API:
```powershell
python scripts\start_verify_live_api.py
```
Web:
```powershell
python scripts\start_verify_live_web.py --api-base http://127.0.0.1:8011
```

### 8) 停止服務
- 在啟動終端按 `Ctrl+C`。
- 若有殘留程序：
```powershell
taskkill /F /T /IM node.exe
taskkill /F /T /IM uvicorn.exe
```

### 9) PowerShell 腳本（可選）
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_verify_live.ps1
```

## Linux 安裝與啟動

### 1) 建立後端虛擬環境
```bash
cd verify_live
python -m venv verify_live_api/.venv
```

### 2) 安裝後端依賴
```bash
verify_live_api/.venv/bin/python -m pip install -r verify_live_api/requirements.txt
```

### 3) 安裝前端依賴
```bash
npm --prefix verify_live_web install
```

### 4) 建立環境變數檔
```bash
cp .env.example .env
```
必填欄位：
- `VERIFY_LIVE_API_BASE_URL`
- `VERIFY_LIVE_API_USER`
- `VERIFY_LIVE_API_PASSWORD`

### 5) 一鍵啟動（建議）
```bash
python scripts/start_verify_live.py
```

### 6) 強制重啟 API（必要時）
```bash
python scripts/start_verify_live.py --restart-api
```

### 7) 分開啟動（可選）
API:
```bash
python scripts/start_verify_live_api.py
```
Web:
```bash
python scripts/start_verify_live_web.py --api-base http://127.0.0.1:8011
```

### 8) 停止服務
- 在啟動終端按 `Ctrl+C`。
- 若有殘留程序：
```bash
pkill -f "vite"
pkill -f "uvicorn app.main:app"
```

## 預設連接埠
- API: `http://127.0.0.1:8011`
- Web: `http://127.0.0.1:5179`

## 重要設定
1. `timerange_end_mode=now` 會在任務啟動時解析為當下 UTC 日期。
2. 支援 Spot 與 Futures；實際可用模式取決於 `trading_mode`、`margin_mode`、交易所設定與策略 `can_short`。
3. 預設容忍度：價格 `10 bps`、數量 `0.5%`（`qty_tolerance_ratio=0.005`）。
4. `config_path / strategy_path / datadir` 路徑解析規則：
   - 絕對路徑：直接使用
   - 相對路徑：依序嘗試
     1) `VERIFY_LIVE_WORKSPACE_ROOT`
     2) `verify_live` 上層目錄
     3) `verify_live` 專案目錄
5. 若 `strategy_path` 找不到策略類別，系統會自動搜尋 `user_data/**/strategies`。
6. `VERIFY_LIVE_CONFIG_ROOTS` 的相對路徑同樣套用上述解析規則。

## 建議驗證流程
1. 載入或建立 Profile。
2. 先執行「比對 Live Config」，確認核心參數一致。
3. 視需求執行「更新 K 線」。
4. 執行「回測驗證」，檢視 Summary 與 Details。

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

## 安全建議
- `.env` 可能包含帳密或 API 金鑰，不應提交至版本控制。
- `.env.example` 僅保留欄位名稱，不放任何真實密鑰。
