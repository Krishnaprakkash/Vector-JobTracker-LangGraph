// frontend/lib/api.ts
const API_BASE = "http://localhost:8000";
export const DEV_USER_ID = "fbf2421e-2961-4e83-941f-af35c60575d5";

export async function refreshJobs() {
  const res = await fetch(`${API_BASE}/api/jobs/refresh?user_id=${DEV_USER_ID}`, { method: "POST" });
  return res.json();
}

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