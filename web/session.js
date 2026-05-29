/** Shared auth token helpers (login + workspace). */
const AUTH_TOKEN_KEY = "ruc_baoyan_auth_token";
const AUTH_USER_KEY = "ruc_baoyan_auth_user";

function getAuthToken() {
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

function getAuthUser() {
  return localStorage.getItem(AUTH_USER_KEY) || "";
}

function setAuthSession(token, username) {
  localStorage.setItem(AUTH_TOKEN_KEY, token || "");
  localStorage.setItem(AUTH_USER_KEY, username || "");
}

function clearAuthSession() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

function authHeaders(extra) {
  const headers = { ...(extra || {}) };
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function parseJsonResponse(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    const snippet = text.length > 280 ? `${text.slice(0, 280)}…` : text;
    throw new Error(
      res.ok
        ? `服务器返回了非 JSON 内容：${snippet}`
        : `请求失败（HTTP ${res.status}）：${snippet}`,
    );
  }
}

async function apiFetch(url, options) {
  const opts = { ...(options || {}) };
  const headers = authHeaders(opts.headers);
  if (opts.body && !(opts.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  opts.headers = headers;
  const res = await fetch(url, opts);
  if (res.status === 401) {
    clearAuthSession();
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/?next=${next}`;
    throw new Error("未登录或会话已过期");
  }
  return res;
}

async function verifyAuthSession() {
  const token = getAuthToken();
  if (!token) return false;
  try {
    const res = await fetch("/api/auth/me", { headers: authHeaders() });
    if (!res.ok) {
      clearAuthSession();
      return false;
    }
    const data = await res.json();
    if (data.username) setAuthSession(token, data.username);
    return true;
  } catch {
    return false;
  }
}
