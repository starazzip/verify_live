import { useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  cancelJob,
  compareProfileConfig,
  createDataJob,
  createJob,
  deleteProfile,
  fetchCompareDetails,
  fetchCompareSummary,
  fetchConfigs,
  fetchDataJobLogTail,
  fetchDataJob,
  fetchDefaults,
  fetchJob,
  fetchJobLogTail,
  fetchProfile,
  fetchProfiles,
  fetchSignals,
  saveProfile,
} from "./api";

const DEFAULT_FORM = {
  profile_name: "",
  config_path: "",
  strategy: "",
  strategy_path: "user_data/strategies",
  timeframe: "5m",
  download_timeframes: "5m,4h,1d",
  timerange_start: "20250101",
  timerange_end_mode: "now",
  timerange_end_fixed: "",
  fee: "",
  datadir: "",
  live_api_base_url: "",
  live_api_username: "",
  live_api_password: "",
  live_strategy_name: "",
  price_tolerance_bps: "10",
  qty_tolerance_ratio: "0.005",
};

const TIMEFRAME_OPTIONS = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"];

function parseTimeframes(value) {
  if (Array.isArray(value)) {
    return [...new Set(value.map((x) => String(x).trim()).filter(Boolean))];
  }
  return [...new Set(String(value || "").split(",").map((x) => x.trim()).filter(Boolean))];
}

function mergeTimeframes(primary, selected, customInput = "") {
  const merged = [];
  const first = String(primary || "").trim() || "5m";
  merged.push(first);
  for (const tf of parseTimeframes(selected)) {
    if (!merged.includes(tf)) merged.push(tf);
  }
  for (const tf of parseTimeframes(customInput)) {
    if (!merged.includes(tf)) merged.push(tf);
  }
  return merged;
}

function lampClass(color) {
  if (color === "green") return "lamp lamp-green";
  if (color === "yellow") return "lamp lamp-yellow";
  return "lamp lamp-red";
}

function fmtNum(value, digits = 4) {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toFixed(digits);
}

function fmtPriceDiff(value) {
  if (value === null || value === undefined || value === "") return "-";
  const bps = Number(value);
  if (!Number.isFinite(bps)) return "-";
  const pct = bps / 100;
  return `${bps.toFixed(2)} bps (${pct.toFixed(4)}%)`;
}

function toStringMap(obj) {
  return Object.fromEntries(
    Object.entries(obj || {}).map(([k, v]) => [k, v === null || v === undefined ? "" : String(v)])
  );
}

function mergeProfileIntoDefaults(defaults, payload) {
  const incoming = toStringMap(payload);
  const merged = { ...defaults };
  for (const [k, v] of Object.entries(incoming)) {
    if (!(k in merged)) continue;
    if (v === "") continue;
    merged[k] = v;
  }
  return merged;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isJobRunningStatus(status) {
  return status === "pending" || status === "running" || status === "cancel_requested";
}

function isDataJobRunningStatus(status) {
  return status === "pending" || status === "running";
}

function fmtAny(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function statusText(status) {
  if (status === "match") return "一致";
  if (status === "mismatch") return "不一致";
  if (status === "not_provided_live") return "不提供";
  if (status === "missing_live") return "Live 缺少";
  if (status === "missing_local") return "Local 缺少";
  if (status === "ignored") return "僅參考";
  return status;
}

function taskTone(status) {
  if (status === "completed") return "ok";
  if (status === "running" || status === "pending" || status === "cancel_requested") return "warn";
  if (status === "failed" || status === "cancelled") return "bad";
  return "idle";
}

export default function App() {
  const [configs, setConfigs] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [defaultForm, setDefaultForm] = useState(DEFAULT_FORM);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [showPassword, setShowPassword] = useState(false);
  const [showTimeframePicker, setShowTimeframePicker] = useState(false);
  const [timeframeDraft, setTimeframeDraft] = useState([]);
  const [timeframeCustomInput, setTimeframeCustomInput] = useState("");
  const [dataJob, setDataJob] = useState(null);
  const [dataJobLogTail, setDataJobLogTail] = useState("");
  const [job, setJob] = useState(null);
  const [jobLogTail, setJobLogTail] = useState("");
  const [configCompare, setConfigCompare] = useState(null);
  const [summary, setSummary] = useState(null);
  const [details, setDetails] = useState([]);
  const [btSignals, setBtSignals] = useState([]);
  const [liveSignals, setLiveSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [workspaceTab, setWorkspaceTab] = useState("monitor");
  const timerRef = useRef(null);
  const dataTimerRef = useRef(null);
  const canStopJob = Boolean(job?.job_id && isJobRunningStatus(job.status));
  const isDataDownloading = Boolean(dataJob?.data_job_id && isDataJobRunningStatus(dataJob.status));
  const hasSignalResult = Boolean(summary || details.length || btSignals.length || liveSignals.length);
  const hasConfigResult = Boolean(configCompare);
  const hasDataJobResult = Boolean(dataJob && ["completed", "failed", "cancelled"].includes(dataJob.status));

  useEffect(() => {
    bootstrap();
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      if (dataTimerRef.current) window.clearInterval(dataTimerRef.current);
    };
  }, []);

  async function bootstrap() {
    setLoading(true);
    setMessage("");
    try {
      const defaults = await fetchDefaults().catch(() => ({}));
      const mergedDefaults = {
        ...DEFAULT_FORM,
        ...toStringMap(defaults),
      };
      setDefaultForm(mergedDefaults);
      setForm(mergedDefaults);
      await reloadConfigsAndProfiles(5);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function reloadConfigsAndProfiles(maxRetry = 3) {
    let lastErr = null;
    for (let i = 0; i < maxRetry; i += 1) {
      try {
        const [c, p] = await Promise.all([fetchConfigs(), fetchProfiles()]);
        setConfigs(c.items || []);
        setProfiles(p.items || []);
        if ((c.items || []).length === 0) {
          setMessage("目前掃描到 0 筆 config，請檢查 API 的 config roots 設定。");
        } else {
          setMessage("");
        }
        return;
      } catch (err) {
        lastErr = err;
        if (i < maxRetry - 1) {
          await sleep(1200);
        }
      }
    }
    if (lastErr) throw lastErr;
  }

  function onConfigSelect(configId) {
    const cfg = configs.find((item) => item.config_id === configId);
    if (!cfg) return;
    setForm((prev) => ({
      ...prev,
      config_path: cfg.config_path || prev.config_path,
      strategy: cfg.strategy || prev.strategy,
      strategy_path: cfg.strategy_path || prev.strategy_path,
      timeframe: cfg.timeframe || prev.timeframe,
      download_timeframes: mergeTimeframes(
        cfg.timeframe || prev.timeframe || "5m",
        prev.download_timeframes || defaultForm.download_timeframes
      ).join(","),
      datadir: cfg.datadir || prev.datadir,
      fee: cfg.fee === null || cfg.fee === undefined ? prev.fee : String(cfg.fee),
    }));
  }

  async function onProfileSelect(profileId) {
    setSelectedProfileId(profileId);
    if (!profileId) {
      setForm(defaultForm);
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const p = await fetchProfile(profileId);
      const payload = p.payload || {};
      setForm(mergeProfileIntoDefaults(defaultForm, payload));
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onDeleteProfile() {
    if (!selectedProfileId) return;
    const ok = window.confirm(`確定刪除 profile：${selectedProfileId}？\n會連同相關 jobs 結果一起刪除。`);
    if (!ok) return;
    setLoading(true);
    setMessage("");
    try {
      await deleteProfile(selectedProfileId);
      setSelectedProfileId("");
      setForm(defaultForm);
      await reloadConfigsAndProfiles(2);
      setMessage("profile 已刪除。");
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function normalizedPayload(overrides = {}) {
    const payload = {
      profile_name: form.profile_name.trim(),
      config_path: form.config_path.trim(),
      strategy: form.strategy.trim(),
      strategy_path: form.strategy_path.trim() || "user_data/strategies",
      timeframe: form.timeframe.trim() || "5m",
      download_timeframes: parseTimeframes(form.download_timeframes),
      timerange_start: form.timerange_start.trim(),
      timerange_end_mode: form.timerange_end_mode === "fixed" ? "fixed" : "now",
      timerange_end_fixed: form.timerange_end_mode === "fixed" ? form.timerange_end_fixed.trim() : null,
      fee: form.fee === "" ? null : Number(form.fee),
      datadir: form.datadir.trim(),
      live_api_base_url: form.live_api_base_url.trim(),
      live_api_username: form.live_api_username.trim(),
      live_api_password: form.live_api_password,
      live_strategy_name: form.live_strategy_name.trim() || null,
      price_tolerance_bps: Number(form.price_tolerance_bps || "10"),
      qty_tolerance_ratio: Number(form.qty_tolerance_ratio || "0.005"),
    };
    return { ...payload, ...overrides };
  }

  async function onSaveProfile() {
    setLoading(true);
    setMessage("");
    try {
      const saved = await saveProfile(normalizedPayload(), selectedProfileId || null);
      setSelectedProfileId(saved.profile_id);
      setMessage(`已儲存 profile：${saved.profile_name} (${saved.profile_id})`);
      const p = await fetchProfiles();
      setProfiles(p.items || []);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function saveSelectedProfileOnly(overrides = {}) {
    if (!selectedProfileId) {
      throw new Error("請先按「儲存Profile」建立 Profile，再執行此操作。");
    }
    const saved = await saveProfile(normalizedPayload(overrides), selectedProfileId);
    setSelectedProfileId(saved.profile_id);
    return saved;
  }

  async function onCompareConfig() {
    setLoading(true);
    setMessage("");
    try {
      const saved = await saveSelectedProfileOnly();
      const result = await compareProfileConfig(saved.profile_id);
      setConfigCompare(result);
      const s = result.summary || {};
      setMessage(
        `Config 比對完成：一致 ${s.match || 0} / ${s.total || 0}，不一致 ${s.mismatch || 0}`
      );
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadJobArtifacts(jobId) {
    const [sum, det, bt, lv] = await Promise.all([
      fetchCompareSummary(jobId),
      fetchCompareDetails(jobId, 3000),
      fetchSignals(jobId, "backtest", 2000),
      fetchSignals(jobId, "live", 2000),
    ]);
    setSummary(sum);
    setDetails(det.items || []);
    setBtSignals(bt.items || []);
    setLiveSignals(lv.items || []);
  }

  function openTimeframePicker() {
    setTimeframeDraft(parseTimeframes(form.download_timeframes || defaultForm.download_timeframes));
    setTimeframeCustomInput("");
    setShowTimeframePicker(true);
  }

  function toggleTimeframeDraft(tf) {
    setTimeframeDraft((prev) => (prev.includes(tf) ? prev.filter((item) => item !== tf) : [...prev, tf]));
  }

  async function onConfirmUpdateKlines() {
    const chosen = mergeTimeframes(form.timeframe, timeframeDraft, timeframeCustomInput);
    setField("download_timeframes", chosen.join(","));
    setShowTimeframePicker(false);
    await onUpdateKlines(chosen);
  }

  async function onUpdateKlines(selectedTimeframes = null) {
    setLoading(true);
    setMessage("");
    setDataJobLogTail("");
    try {
      const payloadOverrides =
        selectedTimeframes && selectedTimeframes.length > 0
          ? { download_timeframes: [...selectedTimeframes] }
          : {};
      const saved = await saveSelectedProfileOnly(payloadOverrides);
      const created = await createDataJob(saved.profile_id);
      setDataJob(created);
      const tfText = (payloadOverrides.download_timeframes || parseTimeframes(form.download_timeframes)).join(",");
      setMessage(`已建立 K 線更新任務：${created.data_job_id}（timeframes: ${tfText || "-"}）`);

      if (dataTimerRef.current) window.clearInterval(dataTimerRef.current);
      dataTimerRef.current = window.setInterval(async () => {
        try {
          const [latest, tail] = await Promise.all([
            fetchDataJob(created.data_job_id),
            fetchDataJobLogTail(created.data_job_id, 35).catch(() => ({ text: "" })),
          ]);
          setDataJob(latest);
          setDataJobLogTail(tail.text || "");
          if (latest.status === "completed" || latest.status === "failed") {
            if (dataTimerRef.current) window.clearInterval(dataTimerRef.current);
            dataTimerRef.current = null;
            if (latest.status === "completed") {
              setMessage(`K 線更新完成：${created.data_job_id}`);
            } else {
              setMessage(`K 線更新失敗：${latest.error || "unknown error"}`);
            }
          }
        } catch (err) {
          if (dataTimerRef.current) window.clearInterval(dataTimerRef.current);
          dataTimerRef.current = null;
          setMessage(err.message);
        }
      }, 2500);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onRunVerify() {
    setLoading(true);
    setMessage("");
    setJobLogTail("");
    setSummary(null);
    setDetails([]);
    setBtSignals([]);
    setLiveSignals([]);
    try {
      const saved = await saveSelectedProfileOnly();
      const created = await createJob(saved.profile_id);
      setJob(created);
      setMessage(`已建立任務：${created.job_id}`);

      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = window.setInterval(async () => {
        try {
          const [latest, tail] = await Promise.all([
            fetchJob(created.job_id),
            fetchJobLogTail(created.job_id, 35).catch(() => ({ text: "" })),
          ]);
          setJob(latest);
          setJobLogTail(tail.text || "");
          if (latest.status === "completed" || latest.status === "failed" || latest.status === "cancelled") {
            if (timerRef.current) window.clearInterval(timerRef.current);
            timerRef.current = null;
            if (latest.status === "completed") {
              await loadJobArtifacts(created.job_id);
              setMessage(`任務完成：${created.job_id}`);
            } else if (latest.status === "cancelled") {
              setMessage(`任務已停止：${created.job_id}`);
            } else {
              setMessage(`任務失敗：${latest.error || "unknown error"}`);
            }
          }
        } catch (err) {
          if (timerRef.current) window.clearInterval(timerRef.current);
          timerRef.current = null;
          setMessage(err.message);
        }
      }, 2500);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onCancelVerify() {
    if (!job?.job_id) return;
    setLoading(true);
    setMessage("");
    try {
      const updated = await cancelJob(job.job_id);
      setJob(updated);
      setMessage(`已送出停止請求：${job.job_id}`);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  const configOptions = useMemo(
    () =>
      configs.map((item) => (
        <option key={item.config_id} value={item.config_id}>
          {item.label}
        </option>
      )),
    [configs]
  );

  return (
    <div className="page">
      <header className="header">
        <h1>verify_live</h1>
        <p>Spot 實盤 vs 回測一致性驗證（同根 K + 價量燈號）</p>
        <p className="muted">API Base: {API_BASE}</p>
      </header>

      <section className="panel control-panel">
        <div className="ops-card profile-card">
          <div className="ops-title">Profile 管理</div>
          <div className="row">
            <label>載入 Profile</label>
            <select value={selectedProfileId} onChange={(e) => onProfileSelect(e.target.value)}>
              <option value="">(新 profile)</option>
              {profiles.map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.profile_name} ({p.profile_id})
                </option>
              ))}
            </select>
          </div>
          <div className="actions">
            <button onClick={onSaveProfile} disabled={loading}>
              儲存Profile
            </button>
            <button onClick={onDeleteProfile} disabled={loading || !selectedProfileId}>
              刪除 Profile
            </button>
          </div>
        </div>

        <div className="selector-grid">
          <div className="row">
            <label>選擇 Config（目前 {configs.length} 筆）</label>
            <select onChange={(e) => onConfigSelect(e.target.value)} defaultValue="">
              <option value="">請選擇 config</option>
              {configOptions}
            </select>
          </div>
        </div>

        <div className="grid">
          <Field label="profile_name" required value={form.profile_name} onChange={(v) => setField("profile_name", v)} />
          <Field label="config_path" required value={form.config_path} onChange={(v) => setField("config_path", v)} />
          <Field label="strategy" required value={form.strategy} onChange={(v) => setField("strategy", v)} />
          <Field label="timeframe" value={form.timeframe} onChange={(v) => setField("timeframe", v)} />
          <Field
            label="download_timeframes（更新K線用）"
            value={form.download_timeframes}
            onChange={(v) => setField("download_timeframes", v)}
          />
          <Field label="timerange_start" required value={form.timerange_start} onChange={(v) => setField("timerange_start", v)} />
          <SelectField
            label="timerange_end_mode"
            value={form.timerange_end_mode}
            onChange={(v) => setField("timerange_end_mode", v)}
            options={[
              { value: "now", text: "now（結束到目前時間）" },
              { value: "fixed", text: "fixed（使用固定結束日）" },
            ]}
            hint="支援模式：now、fixed"
          />
          <Field
            label="timerange_end_fixed"
            required={form.timerange_end_mode === "fixed"}
            value={form.timerange_end_fixed}
            onChange={(v) => setField("timerange_end_fixed", v)}
            placeholder="YYYYMMDD，例如 20251231"
            hint="僅在 timerange_end_mode=fixed 時生效，代表結束日期（含當日）。"
          />

          <Field label="strategy_path" value={form.strategy_path} onChange={(v) => setField("strategy_path", v)} />
          <Field label="fee" value={form.fee} onChange={(v) => setField("fee", v)} />
          <Field label="datadir" value={form.datadir} onChange={(v) => setField("datadir", v)} />
          <Field label="live_api_base_url" value={form.live_api_base_url} onChange={(v) => setField("live_api_base_url", v)} />
          <Field label="live_api_username" value={form.live_api_username} onChange={(v) => setField("live_api_username", v)} />
          <PasswordField
            label="live_api_password"
            value={form.live_api_password}
            visible={showPassword}
            onToggle={() => setShowPassword((v) => !v)}
            onChange={(v) => setField("live_api_password", v)}
          />
          <Field label="live_strategy_name" value={form.live_strategy_name} onChange={(v) => setField("live_strategy_name", v)} />
          <Field label="price_tolerance_bps" value={form.price_tolerance_bps} onChange={(v) => setField("price_tolerance_bps", v)} />
          <Field label="qty_tolerance_ratio" value={form.qty_tolerance_ratio} onChange={(v) => setField("qty_tolerance_ratio", v)} />
        </div>

        <div className="ops-card task-ops-card">
          <div className="ops-title">任務操作</div>
          <div className="task-action-grid">
            <div className="task-action-unit">
              <div className="task-action-title">Config 比對</div>
              <div className="actions compact-actions">
                <button onClick={onCompareConfig} disabled={loading || canStopJob || isDataDownloading || !selectedProfileId}>
                  比對 Live Config
                </button>
              </div>
              <StatusPill
                label="Config 比對"
                value={hasConfigResult ? "已有結果" : "尚未執行"}
                tone={hasConfigResult ? "ok" : "idle"}
                actionLabel={hasConfigResult ? "查看結果" : "查看狀態"}
                onAction={() => setWorkspaceTab("config")}
              />
            </div>

            <div className="task-action-unit">
              <div className="task-action-title">K 線更新</div>
              <div className="actions compact-actions">
                <button onClick={openTimeframePicker} disabled={loading || canStopJob || isDataDownloading || !selectedProfileId}>
                  更新 K 線
                </button>
              </div>
              <StatusPill
                label="K線更新"
                value={dataJob?.status || "尚未建立"}
                tone={taskTone(dataJob?.status)}
                actionLabel={hasDataJobResult ? "查看結果" : "查看狀態"}
                actionDisabled={!dataJob}
                onAction={() => setWorkspaceTab("monitor")}
              />
            </div>

            <div className="task-action-unit">
              <div className="task-action-title">回測驗證</div>
              <div className="actions compact-actions">
                <button className="btn-primary" onClick={onRunVerify} disabled={loading || canStopJob || isDataDownloading || !selectedProfileId}>
                  回測驗證
                </button>
                <button onClick={onCancelVerify} disabled={loading || !canStopJob}>
                  停止驗證
                </button>
              </div>
              <StatusPill
                label="回測任務"
                value={job?.status || "尚未建立"}
                tone={taskTone(job?.status)}
                actionLabel={hasSignalResult ? "查看結果" : "查看狀態"}
                actionDisabled={!job && !hasSignalResult}
                onAction={() => setWorkspaceTab(hasSignalResult ? "signals" : "monitor")}
              />
            </div>
          </div>
        </div>

        {message && <div className="msg">{message}</div>}
      </section>

      <section className="panel workspace-panel">
        <div className="workspace-head">
          <h2>工作台</h2>
          <div className="muted">
            目前檢視：
            {workspaceTab === "monitor" && " 任務監看"}
            {workspaceTab === "config" && " Config 比對"}
            {workspaceTab === "signals" && " 訊號比對"}
          </div>
        </div>

        {workspaceTab === "monitor" && (
          <div className="task-grid">
            <TaskCard
              title="K 線更新任務"
              status={dataJob?.status}
              lines={[
                { label: "data_job_id", value: dataJob?.data_job_id || "-" },
                { label: "timeframe", value: dataJob?.timeframe || "-" },
                { label: "timerange", value: `${dataJob?.resolved_timerange_start || "-"} - ${dataJob?.resolved_timerange_end || "-"}` },
                { label: "error", value: dataJob?.error || "-" },
              ]}
              logTitle="Freqtrade 即時輸出（最後 35 行）"
              logText={dataJobLogTail}
            />
            <TaskCard
              title="回測驗證任務"
              status={job?.status}
              lines={[
                { label: "job_id", value: job?.job_id || "-" },
                { label: "timerange", value: `${job?.resolved_timerange_start || "-"} - ${job?.resolved_timerange_end || "-"}` },
                { label: "error", value: job?.error || "-" },
              ]}
              logTitle="Freqtrade 即時輸出（最後 35 行）"
              logText={jobLogTail}
            />
          </div>
        )}

        {workspaceTab === "config" && (
          <>
            <h3 className="sub-title">Config 比對（Local vs Live）</h3>
            {!configCompare && <div className="muted">按「比對 Live Config」後顯示</div>}
            {configCompare && (
              <>
                <div className="summary-grid">
                  <SummaryItem label="總欄位" value={configCompare.summary?.total || 0} />
                  <SummaryItem label="一致" value={configCompare.summary?.match || 0} />
                  <SummaryItem label="不一致" value={configCompare.summary?.mismatch || 0} />
                  <SummaryItem label="不提供" value={configCompare.summary?.not_provided_live || 0} />
                  <SummaryItem label="Live 缺少" value={configCompare.summary?.missing_live || 0} />
                  <SummaryItem label="Local 缺少" value={configCompare.summary?.missing_local || 0} />
                </div>
                <div className="muted config-note">local: {configCompare.resolved_config_path}</div>
                <div className="muted config-note">live: {configCompare.live_api_base_url}</div>
                <div className="muted config-note">
                  註：Live 端使用 `show_config`，回傳的是運行相關設定子集，部分欄位可能不存在。
                </div>
                <div className="muted config-note">藍燈（不提供）代表此欄位為官方 `show_config` 設計上不回傳（原因顯示為 LIVE不提供）。</div>
                {configCompare.pairlist_compare && (
                  <div className="pairlist-box">
                    <div className="pairlist-row">
                      <strong>白名單</strong>
                      <span className="muted">
                        {configCompare.pairlist_compare.whitelist?.enforced === false ? "（不作為一致性條件）" : ""}
                      </span>
                      <span className={`status-chip status-${configCompare.pairlist_compare.whitelist?.status || "mismatch"}`}>
                        {statusText(configCompare.pairlist_compare.whitelist?.status)}
                      </span>
                      <span>local: {configCompare.pairlist_compare.whitelist?.local_count || 0}</span>
                      <span>live: {configCompare.pairlist_compare.whitelist?.live_count || 0}</span>
                      <span>only_local: {configCompare.pairlist_compare.whitelist?.only_local_count || 0}</span>
                      <span>only_live: {configCompare.pairlist_compare.whitelist?.only_live_count || 0}</span>
                    </div>
                    <div className="pairlist-row">
                      <strong>黑名單</strong>
                      <span className={`status-chip status-${configCompare.pairlist_compare.blacklist?.status || "mismatch"}`}>
                        {statusText(configCompare.pairlist_compare.blacklist?.status)}
                      </span>
                      <span>local: {configCompare.pairlist_compare.blacklist?.local_count || 0}</span>
                      <span>live: {configCompare.pairlist_compare.blacklist?.live_count || 0}</span>
                      <span>only_local: {configCompare.pairlist_compare.blacklist?.only_local_count || 0}</span>
                      <span>only_live: {configCompare.pairlist_compare.blacklist?.only_live_count || 0}</span>
                    </div>
                    {((configCompare.pairlist_compare.whitelist?.only_local_sample || []).length > 0 ||
                      (configCompare.pairlist_compare.whitelist?.only_live_sample || []).length > 0) && (
                      <div className="pairlist-diff">
                        <div className="muted">白名單差異（sample）</div>
                        <div>only_local: {(configCompare.pairlist_compare.whitelist?.only_local_sample || []).join(", ") || "-"}</div>
                        <div>only_live: {(configCompare.pairlist_compare.whitelist?.only_live_sample || []).join(", ") || "-"}</div>
                      </div>
                    )}
                    {((configCompare.pairlist_compare.blacklist?.only_local_sample || []).length > 0 ||
                      (configCompare.pairlist_compare.blacklist?.only_live_sample || []).length > 0) && (
                      <div className="pairlist-diff">
                        <div className="muted">黑名單差異（sample）</div>
                        <div>only_local: {(configCompare.pairlist_compare.blacklist?.only_local_sample || []).join(", ") || "-"}</div>
                        <div>only_live: {(configCompare.pairlist_compare.blacklist?.only_live_sample || []).join(", ") || "-"}</div>
                      </div>
                    )}
                  </div>
                )}
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>欄位</th>
                        <th>Local</th>
                        <th>Live</th>
                        <th>結果</th>
                        <th>說明</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(configCompare.items || []).map((row, idx) => (
                        <tr key={`${row.field}-${idx}`}>
                          <td>{row.field}</td>
                          <td>{fmtAny(row.local_value)}</td>
                          <td>{fmtAny(row.live_value)}</td>
                          <td>
                            <span className={`status-chip status-${row.status}`}>{statusText(row.status)}</span>
                          </td>
                          <td>{row.reason || "-"}</td>
                        </tr>
                      ))}
                      {(configCompare.items || []).length === 0 && (
                        <tr>
                          <td colSpan={5} className="muted center">
                            尚無欄位可比對
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}

        {workspaceTab === "signals" && (
          <>
            <h3 className="sub-title">比對摘要</h3>
            {!summary && <div className="muted">任務完成後顯示</div>}
            {summary && (
              <div className="summary-grid">
                <SummaryItem label="總筆數" value={summary.total_rows} />
                <SummaryItem label="訊號綠燈" value={summary.signal_green} />
                <SummaryItem label="訊號紅燈" value={summary.signal_red} />
                <SummaryItem label="成交綠燈" value={summary.fill_green} />
                <SummaryItem label="成交黃燈" value={summary.fill_yellow} />
                <SummaryItem label="成交紅燈" value={summary.fill_red} />
                <SummaryItem label="訊號一致率" value={`${fmtNum((summary.signal_match_rate || 0) * 100, 2)}%`} />
                <SummaryItem label="成交綠燈率" value={`${fmtNum((summary.fill_green_rate || 0) * 100, 2)}%`} />
                <SummaryItem label="Backtest 訊號數" value={btSignals.length} />
                <SummaryItem label="Live 訊號數" value={liveSignals.length} />
              </div>
            )}

            <h3 className="sub-title">比對明細（前 3000 筆）</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>pair</th>
                    <th>side</th>
                    <th>bucket</th>
                    <th>訊號燈</th>
                    <th>成交燈</th>
                    <th>價格差(bps / %)</th>
                    <th>數量差(%)</th>
                    <th>狀態</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {details.map((row, idx) => (
                    <tr key={`${row.pair}-${row.side}-${row.bucket_ts}-${idx}`}>
                      <td>{row.pair}</td>
                      <td>{row.side}</td>
                      <td>{row.bucket_ts}</td>
                      <td>
                        <span className={lampClass(row.signal_lamp)} />
                      </td>
                      <td>
                        <span className={lampClass(row.fill_lamp)} />
                      </td>
                      <td>{fmtPriceDiff(row.price_diff_bps)}</td>
                      <td>{fmtNum((row.qty_diff_ratio || 0) * 100, 2)}</td>
                      <td>{row.signal_state}</td>
                      <td>{row.reason}</td>
                    </tr>
                  ))}
                  {details.length === 0 && (
                    <tr>
                      <td colSpan={9} className="muted center">
                        尚無資料
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {showTimeframePicker && (
        <div className="modal-backdrop" onClick={() => setShowTimeframePicker(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>選擇更新 K 線的 Timeframes</h3>
            <div className="muted">
              主 timeframe（{form.timeframe || "5m"}）會自動包含。可多選，或在下方自訂輸入。
            </div>
            <div className="tf-grid">
              {TIMEFRAME_OPTIONS.map((tf) => {
                const checked =
                  tf === (form.timeframe || "5m") ||
                  timeframeDraft.includes(tf);
                return (
                  <label key={tf} className="tf-item">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={tf === (form.timeframe || "5m")}
                      onChange={() => toggleTimeframeDraft(tf)}
                    />
                    <span>{tf}</span>
                  </label>
                );
              })}
            </div>
            <div className="row">
              <label>自訂 Timeframes（逗號分隔）</label>
              <input
                value={timeframeCustomInput}
                onChange={(e) => setTimeframeCustomInput(e.target.value)}
                placeholder="例如: 2h,12h"
              />
            </div>
            <div className="actions">
              <button onClick={() => setShowTimeframePicker(false)}>取消</button>
              <button className="btn-primary" onClick={onConfirmUpdateKlines}>
                確認並更新
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function FieldLabel({ label, required = false }) {
  return (
    <label>
      {label}
      {required ? <span className="field-required">*</span> : <span className="field-optional">(optional)</span>}
    </label>
  );
}

function StatusPill({ label, value, tone = "idle", actionLabel = "", onAction = null, actionDisabled = false }) {
  return (
    <div className={`status-pill tone-${tone}`}>
      <div className="status-pill-label">{label}</div>
      <div className="status-pill-value">{value}</div>
      {actionLabel ? (
        <button type="button" className="status-pill-action" onClick={onAction || undefined} disabled={actionDisabled}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

function TaskCard({ title, status, lines, logTitle, logText }) {
  return (
    <article className="task-card">
      <div className="task-card-head">
        <h3>{title}</h3>
        <span className={`status-chip task-chip-${taskTone(status)}`}>{status || "尚未建立"}</span>
      </div>

      <div className="jobbox">
        {lines.map((item) => (
          <div key={`${title}-${item.label}`}>
            {item.label}: {item.value}
          </div>
        ))}
      </div>

      <details className="task-log" open={status === "running" || status === "pending" || status === "cancel_requested"}>
        <summary>{logTitle}</summary>
        <pre className="log-tail">{logText || "(尚無輸出)"}</pre>
      </details>
    </article>
  );
}

function Field({ label, value, onChange, required = false, hint = "", placeholder = "" }) {
  return (
    <div className="field">
      <FieldLabel label={label} required={required} />
      <input value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      {hint ? <div className="field-hint">{hint}</div> : null}
    </div>
  );
}

function SelectField({ label, value, onChange, options = [], required = false, hint = "" }) {
  return (
    <div className="field">
      <FieldLabel label={label} required={required} />
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((item) => (
          <option key={item.value} value={item.value}>
            {item.text}
          </option>
        ))}
      </select>
      {hint ? <div className="field-hint">{hint}</div> : null}
    </div>
  );
}

function PasswordField({ label, value, visible, onToggle, onChange, required = false, hint = "" }) {
  return (
    <div className="field">
      <FieldLabel label={label} required={required} />
      <div className="password-wrap">
        <input type={visible ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="btn-inline" onClick={onToggle}>
          {visible ? "隱藏" : "顯示"}
        </button>
      </div>
      {hint ? <div className="field-hint">{hint}</div> : null}
    </div>
  );
}

function SummaryItem({ label, value }) {
  return (
    <div className="summary-item">
      <div className="summary-label">{label}</div>
      <div className="summary-value">{value}</div>
    </div>
  );
}
