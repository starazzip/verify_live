export const API_BASE = import.meta.env.VITE_VERIFY_LIVE_API_BASE || "http://127.0.0.1:8011";

async function request(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, options);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const msg = data.detail || data.error || `API 失敗: ${path}`;
    throw new Error(msg);
  }
  return data;
}

export function fetchConfigs() {
  return request("/api/verify/configs");
}

export function fetchDefaults() {
  return request("/api/verify/defaults");
}

export function fetchProfiles() {
  return request("/api/verify/profiles");
}

export function fetchProfile(profileId) {
  return request(`/api/verify/profiles/${encodeURIComponent(profileId)}`);
}

export function saveProfile(payload, profileId) {
  return request("/api/verify/profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      profile_id: profileId || null,
      payload,
    }),
  });
}

export function deleteProfile(profileId) {
  return request(`/api/verify/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
}

export function compareProfileConfig(profileId) {
  return request(`/api/verify/profiles/${encodeURIComponent(profileId)}/config-compare`, {
    method: "POST",
  });
}

export function createJob(profileId) {
  return request("/api/verify/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export function createDataJob(profileId) {
  return request("/api/verify/data-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export function fetchJob(jobId) {
  return request(`/api/verify/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchJobLogTail(jobId, lines = 30) {
  return request(
    `/api/verify/jobs/${encodeURIComponent(jobId)}/logs/tail?lines=${encodeURIComponent(lines)}`
  );
}

export function fetchDataJob(dataJobId) {
  return request(`/api/verify/data-jobs/${encodeURIComponent(dataJobId)}`);
}

export function fetchDataJobLogTail(dataJobId, lines = 30) {
  return request(
    `/api/verify/data-jobs/${encodeURIComponent(dataJobId)}/logs/tail?lines=${encodeURIComponent(lines)}`
  );
}

export function cancelJob(jobId) {
  return request(`/api/verify/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  });
}

export function fetchSignals(jobId, source, limit = 2000) {
  return request(
    `/api/verify/jobs/${encodeURIComponent(jobId)}/signals?source=${encodeURIComponent(
      source
    )}&limit=${limit}`
  );
}

export function fetchCompareSummary(jobId) {
  return request(`/api/verify/jobs/${encodeURIComponent(jobId)}/compare/summary`);
}

export function fetchCompareDetails(jobId, limit = 2000) {
  return request(
    `/api/verify/jobs/${encodeURIComponent(jobId)}/compare/details?limit=${limit}`
  );
}
