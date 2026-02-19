import { useEffect, useMemo, useRef, useState } from "react";
import {
  createJob,
  fetchCompareDetails,
  fetchCompareSummary,
  fetchConfigs,
  fetchJob,
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
  timerange_start: "20250101",
  timerange_end_mode: "now",
  timerange_end_fixed: "",
  fee: "",
  datadir: "",
  live_api_base_url: "",
  live_api_username: "",
  live_api_password_env: "VERIFY_LIVE_API_PASSWORD",
  live_strategy_name: "",
  price_tolerance_bps: "10",
  qty_tolerance_ratio: "0.005",
};

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

export default function App() {
  const [configs, setConfigs] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [form, setForm] = useState(DEFAULT_FORM);
  const [job, setJob] = useState(null);
  const [summary, setSummary] = useState(null);
  const [details, setDetails] = useState([]);
  const [btSignals, setBtSignals] = useState([]);
  const [liveSignals, setLiveSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const timerRef = useRef(null);

  useEffect(() => {
    reloadConfigsAndProfiles();
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

  async function reloadConfigsAndProfiles() {
    setLoading(true);
    setMessage("");
    try {
      const [c, p] = await Promise.all([fetchConfigs(), fetchProfiles()]);
      setConfigs(c.items || []);
      setProfiles(p.items || []);
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
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
      datadir: cfg.datadir || prev.datadir,
      fee: cfg.fee === null || cfg.fee === undefined ? prev.fee : String(cfg.fee),
    }));
  }

  async function onProfileSelect(profileId) {
    setSelectedProfileId(profileId);
    if (!profileId) return;
    setLoading(true);
    setMessage("");
    try {
      const p = await fetchProfile(profileId);
      const payload = p.payload || {};
      setForm({
        ...DEFAULT_FORM,
        ...Object.fromEntries(
          Object.entries(payload).map(([k, v]) => [k, v === null || v === undefined ? "" : String(v)])
        ),
      });
    } catch (err) {
      setMessage(err.message);
    } finally {
      setLoading(false);
    }
  }

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function normalizedPayload() {
    return {
      profile_name: form.profile_name.trim(),
      config_path: form.config_path.trim(),
      strategy: form.strategy.trim(),
      strategy_path: form.strategy_path.trim() || "user_data/strategies",
      timeframe: form.timeframe.trim() || "5m",
      timerange_start: form.timerange_start.trim(),
      timerange_end_mode: form.timerange_end_mode === "fixed" ? "fixed" : "now",
      timerange_end_fixed: form.timerange_end_mode === "fixed" ? form.timerange_end_fixed.trim() : null,
      fee: form.fee === "" ? null : Number(form.fee),
      datadir: form.datadir.trim(),
      live_api_base_url: form.live_api_base_url.trim(),
      live_api_username: form.live_api_username.trim(),
      live_api_password_env: form.live_api_password_env.trim() || "VERIFY_LIVE_API_PASSWORD",
      live_strategy_name: form.live_strategy_name.trim() || null,
      price_tolerance_bps: Number(form.price_tolerance_bps || "10"),
      qty_tolerance_ratio: Number(form.qty_tolerance_ratio || "0.005"),
    };
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

  async function onRunVerify() {
    setLoading(true);
    setMessage("");
    setSummary(null);
    setDetails([]);
    setBtSignals([]);
    setLiveSignals([]);
    try {
      const saved = await saveProfile(normalizedPayload(), selectedProfileId || null);
      setSelectedProfileId(saved.profile_id);
      const created = await createJob(saved.profile_id);
      setJob(created);
      setMessage(`已建立任務：${created.job_id}`);

      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = window.setInterval(async () => {
        try {
          const latest = await fetchJob(created.job_id);
          setJob(latest);
          if (latest.status === "completed" || latest.status === "failed") {
            if (timerRef.current) window.clearInterval(timerRef.current);
            timerRef.current = null;
            if (latest.status === "completed") {
              await loadJobArtifacts(created.job_id);
              setMessage(`任務完成：${created.job_id}`);
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
      </header>

      <section className="panel">
        <div className="row">
          <label>選擇 Config</label>
          <select onChange={(e) => onConfigSelect(e.target.value)} defaultValue="">
            <option value="">請選擇 config</option>
            {configOptions}
          </select>
        </div>

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

        <div className="grid">
          <Field label="profile_name" value={form.profile_name} onChange={(v) => setField("profile_name", v)} />
          <Field label="config_path" value={form.config_path} onChange={(v) => setField("config_path", v)} />
          <Field label="strategy" value={form.strategy} onChange={(v) => setField("strategy", v)} />
          <Field label="strategy_path" value={form.strategy_path} onChange={(v) => setField("strategy_path", v)} />
          <Field label="timeframe" value={form.timeframe} onChange={(v) => setField("timeframe", v)} />
          <Field label="timerange_start" value={form.timerange_start} onChange={(v) => setField("timerange_start", v)} />
          <Field label="timerange_end_mode" value={form.timerange_end_mode} onChange={(v) => setField("timerange_end_mode", v)} />
          <Field label="timerange_end_fixed" value={form.timerange_end_fixed} onChange={(v) => setField("timerange_end_fixed", v)} />
          <Field label="fee" value={form.fee} onChange={(v) => setField("fee", v)} />
          <Field label="datadir" value={form.datadir} onChange={(v) => setField("datadir", v)} />
          <Field label="live_api_base_url" value={form.live_api_base_url} onChange={(v) => setField("live_api_base_url", v)} />
          <Field label="live_api_username" value={form.live_api_username} onChange={(v) => setField("live_api_username", v)} />
          <Field label="live_api_password_env" value={form.live_api_password_env} onChange={(v) => setField("live_api_password_env", v)} />
          <Field label="live_strategy_name" value={form.live_strategy_name} onChange={(v) => setField("live_strategy_name", v)} />
          <Field label="price_tolerance_bps" value={form.price_tolerance_bps} onChange={(v) => setField("price_tolerance_bps", v)} />
          <Field label="qty_tolerance_ratio" value={form.qty_tolerance_ratio} onChange={(v) => setField("qty_tolerance_ratio", v)} />
        </div>

        <div className="actions">
          <button onClick={onSaveProfile} disabled={loading}>
            儲存配置
          </button>
          <button className="btn-primary" onClick={onRunVerify} disabled={loading}>
            回測驗證
          </button>
        </div>

        {message && <div className="msg">{message}</div>}
      </section>

      <section className="panel">
        <h2>任務狀態</h2>
        {!job && <div className="muted">尚未建立任務</div>}
        {job && (
          <div className="jobbox">
            <div>job_id: {job.job_id}</div>
            <div>status: {job.status}</div>
            <div>timerange: {job.resolved_timerange_start || "-"} - {job.resolved_timerange_end || "-"}</div>
            <div>error: {job.error || "-"}</div>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>比對摘要</h2>
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
      </section>

      <section className="panel">
        <h2>比對明細（前 3000 筆）</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>pair</th>
                <th>side</th>
                <th>bucket</th>
                <th>訊號燈</th>
                <th>成交燈</th>
                <th>價格差(bps)</th>
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
                  <td>{fmtNum(row.price_diff_bps, 2)}</td>
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
      </section>
    </div>
  );
}

function Field({ label, value, onChange }) {
  return (
    <div className="field">
      <label>{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)} />
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

