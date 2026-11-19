/**
 * Shared Fetch API client for AI E-Commerce Intelligence System.
 * Handles base URL resolution (same-origin on FastAPI or configurable local backend),
 * JWT Bearer headers, JSON/multipart requests, error normalization, and file downloads.
 */
(function (global) {
  const TOKEN_KEY = 'ciq_access_token';
  const USER_KEY = 'ciq_current_user';
  const API_BASE_KEY = 'ciq_api_base_url';

  function normalizeApiBase(raw) {
    if (!raw) return '';
    let cleaned = raw.trim().replace(/\/+$/, '');
    cleaned = cleaned.replace(/\/(api|auth)$/i, '');
    return cleaned;
  }

  function getApiBase() {
    const custom = localStorage.getItem(API_BASE_KEY);
    if (custom !== null && custom.trim() !== '') {
      return normalizeApiBase(custom);
    }
    const { protocol, hostname, port } = window.location;
    // Same-origin when served directly by FastAPI on port 8000
    if (port === '8000') {
      return '';
    }
    // Local file or local dev server (e.g. :3000, :5173, :5500, :8080) -> target local FastAPI on :8000
    if (protocol === 'file:' || hostname === 'localhost' || hostname === '127.0.0.1') {
      return `http://${hostname || '127.0.0.1'}:8000`;
    }
    // Hosted reverse-proxy origin: default to same-origin
    return '';
  }

  function setApiBase(url) {
    const normalized = normalizeApiBase(url);
    if (!normalized) {
      localStorage.removeItem(API_BASE_KEY);
    } else {
      localStorage.setItem(API_BASE_KEY, normalized);
    }
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setSession(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getStoredUser() {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function formatDetail(detail) {
    if (!detail) return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === 'object') {
            const loc = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body').join('.') : '';
            return loc ? `${loc}: ${item.msg || JSON.stringify(item)}` : item.msg || JSON.stringify(item);
          }
          return String(item);
        })
        .join('; ');
    }
    return JSON.stringify(detail);
  }

  async function parseResponse(response) {
    const contentType = response.headers.get('content-type') || '';
    let payload = null;
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      const text = await response.text();
      payload = text ? { detail: text } : null;
    }

    if (!response.ok) {
      if (response.status === 401 && !window.location.pathname.endsWith('index.html') && window.location.pathname !== '/') {
        clearSession();
        window.location.href = '/frontend/index.html';
        throw new Error('Session expired. Please sign in again.');
      }

      if (response.status === 404 && !contentType.includes('application/json')) {
        const err404 = new Error(
          `Backend API endpoint not found (404) at ${response.url}. The current server is only serving static files. Start FastAPI locally with "uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload" and set Backend Server URL to http://127.0.0.1:8000.`
        );
        err404.status = 404;
        throw err404;
      }

      const rawMsg = payload && (payload.detail || payload.message || payload.error);
      const message = formatDetail(rawMsg) || `Request failed with status ${response.status}`;
      const err = new Error(message);
      err.status = response.status;
      err.payload = payload;
      throw err;
    }
    return payload;
  }

  async function request(path, options = {}) {
    const url = `${getApiBase()}${path}`;
    const headers = Object.assign({}, options.headers || {});
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    let response;
    try {
      response = await fetch(url, {
        method: options.method || 'GET',
        headers,
        body:
          options.body && !(options.body instanceof FormData) && typeof options.body !== 'string'
            ? JSON.stringify(options.body)
            : options.body,
      });
    } catch (networkErr) {
      const err = new Error(
        `Cannot reach FastAPI backend at ${getApiBase() || window.location.origin}. Ensure FastAPI/Uvicorn is running locally (uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload).`
      );
      err.isNetworkError = true;
      throw err;
    }
    return parseResponse(response);
  }

  async function downloadFile(path, fallbackFilename) {
    const url = `${getApiBase()}${path}`;
    const headers = {};
    const token = getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const response = await fetch(url, { method: 'GET', headers });
    if (!response.ok) {
      await parseResponse(response);
      return;
    }
    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    let filename = fallbackFilename || 'report';
    const match = disposition.match(/filename="?([^"]+)"?/i);
    if (match && match[1]) {
      filename = match[1];
    }
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1500);
  }

  global.API = {
    getApiBase,
    setApiBase,
    getToken,
    setSession,
    clearSession,
    getStoredUser,
    request,
    get: (path) => request(path, { method: 'GET' }),
    post: (path, body) => request(path, { method: 'POST', body }),
    put: (path, body) => request(path, { method: 'PUT', body }),
    del: (path) => request(path, { method: 'DELETE' }),
    upload: (path, formData) => request(path, { method: 'POST', body: formData }),
    downloadFile,
  };
})(window);
