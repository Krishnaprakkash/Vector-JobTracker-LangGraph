// frontend/lib/api.ts
const API_BASE = "http://localhost:8000";
export const DEV_USER_ID = "fbf2421e-2961-4e83-941f-af35c60575d5";

export async function clearJobs() {
  const res = await fetch(`${API_BASE}/api/jobs/clear?user_id=${DEV_USER_ID}`, { method: "POST" });
  return res.json();
}

export async function getTaskStatus(taskId: string) {
  const res = await fetch(`${API_BASE}/api/jobs/status/${taskId}`);
  return res.json();
}

export async function getJobs() {
  const res = await fetch(`${API_BASE}/api/jobs?user_id=${DEV_USER_ID}`);
  return res.json();
}

export async function getMe() {
  const res = await fetch(`${API_BASE}/api/user/me?user_id=${DEV_USER_ID}`);
  return res.json();
}

export async function updateSearchQuery(query: string) {
  const res = await fetch(`${API_BASE}/api/user/me?user_id=${DEV_USER_ID}&last_search_query=${encodeURIComponent(query)}`, {
    method: "PATCH",
  });
  return res.json();
}

export async function getTrackedJobs() {
  const res = await fetch(`${API_BASE}/api/jobs/tracked?user_id=${DEV_USER_ID}`);
  return res.json();
}

export async function updateJobStatus(jobId: string, status: string) {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}/status?user_id=${DEV_USER_ID}&status=${status}`, {
    method: "PATCH",
  });
  return res.json();
}

export async function deleteJob(jobId: string) {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}?user_id=${DEV_USER_ID}`, {
    method: "DELETE",
  });
  return res.json();
}

export async function getResumes() {
  const res = await fetch(`${API_BASE}/api/resumes?user_id=${DEV_USER_ID}`);
  return res.json();
}

export async function addManualJob(data: {
  company: string; title: string; location: string; resume_id: string;
  raw_input: string; comp_min?: number; comp_max?: number; comp_currency?: string;
}) {
  const params = new URLSearchParams({
    user_id: DEV_USER_ID, company: data.company, title: data.title,
    location: data.location, resume_id: data.resume_id, raw_input: data.raw_input,
  });
  if (data.comp_min) params.set("comp_min", String(data.comp_min));
  if (data.comp_max) params.set("comp_max", String(data.comp_max));
  if (data.comp_currency) params.set("comp_currency", data.comp_currency);

  const res = await fetch(`${API_BASE}/api/jobs/manual?${params}`, { method: "POST" });
  return res.json();
}