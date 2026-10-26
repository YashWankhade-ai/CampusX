/**
 * CampusX API Client — v1.0
 * Centralized HTTP client for all backend API calls.
 * All fetch calls go through this module — never call fetch directly from pages.
 */

(function (global) {
  'use strict';

  // ── Configuration ─────────────────────────────────────────────
  const REMOTE_API_URL = (global.CAMPUSX_API_URL || global.__VITE_API_URL || (typeof process !== 'undefined' && process.env && process.env.VITE_API_URL) || '').replace(/\/+$/, '');
  const BASE_URL = REMOTE_API_URL ? `${REMOTE_API_URL}/api/v1` : '/api/v1';

  // ── Token storage ──────────────────────────────────────────────
  const STORAGE_KEYS = {
    ACCESS:  'cx_access_token',
    REFRESH: 'cx_refresh_token',
    USER:    'cx_user',
  };

  const Storage = {
    get: (k) => {
      try {
        const val = localStorage.getItem(k);
        if (val) return val;
      } catch {}
      try {
        const val = sessionStorage.getItem(k);
        if (val) return val;
      } catch {}
      if (k === STORAGE_KEYS.ACCESS) {
        const match = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
        if (match) return decodeURIComponent(match[1]);
      }
      if (k === STORAGE_KEYS.REFRESH) {
        const match = document.cookie.match(/(?:^|;\s*)refresh_token=([^;]+)/);
        if (match) return decodeURIComponent(match[1]);
      }
      return null;
    },
    set: (k, v) => {
      try { localStorage.setItem(k, v); } catch {}
      try { sessionStorage.setItem(k, v); } catch {}
    },
    remove: (k) => {
      try { localStorage.removeItem(k); } catch {}
      try { sessionStorage.removeItem(k); } catch {}
    },
    clear: () => {
      Object.values(STORAGE_KEYS).forEach(k => {
        try { localStorage.removeItem(k); } catch {}
        try { sessionStorage.removeItem(k); } catch {}
      });
      try {
        document.cookie = 'access_token=; path=/; max-age=0; SameSite=Lax';
        document.cookie = 'refresh_token=; path=/; max-age=0; SameSite=Lax';
        document.cookie = 'cx_role=; path=/; max-age=0; SameSite=Lax';
      } catch {}
    },
  };

  // ── Auth helpers ───────────────────────────────────────────────
  const Auth = {
    getAccessToken: () => Storage.get(STORAGE_KEYS.ACCESS),
    getRefreshToken: () => Storage.get(STORAGE_KEYS.REFRESH),
    getUser: () => {
      try {
        const raw = Storage.get(STORAGE_KEYS.USER);
        if (raw) return JSON.parse(raw);
      } catch {}
      // Fallback: decode JWT payload from access token
      const token = Auth.getAccessToken();
      if (token) {
        try {
          const parts = token.split('.');
          if (parts.length === 3) {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            return {
              id: payload.sub,
              email: payload.email,
              role: payload.role,
              institution_id: payload.institution_id,
            };
          }
        } catch {}
      }
      return null;
    },
    setSession: (accessToken, refreshToken, user) => {
      Storage.set(STORAGE_KEYS.ACCESS, accessToken);
      if (refreshToken) Storage.set(STORAGE_KEYS.REFRESH, refreshToken);
      if (user) Storage.set(STORAGE_KEYS.USER, JSON.stringify(user));
      try {
        document.cookie = `access_token=${accessToken}; path=/; max-age=900; SameSite=Lax`;
        if (refreshToken) document.cookie = `refresh_token=${refreshToken}; path=/; max-age=1209600; SameSite=Lax`;
        if (user && user.role) document.cookie = `cx_role=${user.role}; path=/; max-age=1209600; SameSite=Lax`;
      } catch (e) {}
    },
    clearSession: () => {
      Storage.clear();
    },
    isAuthenticated: () => !!Auth.getAccessToken(),
    getRole: () => {
      const user = Auth.getUser();
      if (user && user.role) return user.role.toUpperCase();
      const match = document.cookie.match(/(?:^|;\s*)cx_role=([^;]+)/);
      if (match) return decodeURIComponent(match[1]).toUpperCase();
      return null;
    },
  };

  // ── Role-based redirect ────────────────────────────────────────
  function dashboardForRole(role) {
    switch ((role || '').toUpperCase()) {
      case 'FACULTY':            return '/faculty/dashboard';
      case 'ADMIN':              return '/admin/dashboard';
      case 'DEPARTMENT_ADMIN':   return '/admin/dashboard';
      case 'INSTITUTION_ADMIN':  return '/admin/dashboard';
      case 'SUPER_ADMIN':        return '/admin/dashboard';
      default:                   return '/student/dashboard';
    }
  }

  // ── Core request ──────────────────────────────────────────────

  async function request(method, path, body, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...opts.headers };
    const token = Auth.getAccessToken();
    if (token && !opts.noAuth) headers['Authorization'] = `Bearer ${token}`;

    let res;
    try {
      res = await fetch(`${BASE_URL}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (err) {
      // Network error
      throw { type: 'NETWORK_ERROR', message: 'Unable to connect. Please check your internet connection.' };
    }

    // 204 No Content
    if (res.status === 204) return { ok: true, data: null };

    let json;
    try { json = await res.json(); } catch {
      throw { type: 'PARSE_ERROR', message: 'Unexpected server response.' };
    }

    if (!res.ok) {
      const code = json.error?.code || json.code || 'API_ERROR';
      const message = json.error?.message || json.message || 'An error occurred. Please try again.';
      const err = { type: code, message, status: res.status };

      // Token expired — attempt silent refresh
      if (res.status === 401 && !opts._retry && !opts.noAuth) {
        const refreshed = await _silentRefresh();
        if (refreshed) {
          opts._retry = true;
          return request(method, path, body, opts);
        } else {
          Auth.clearSession();
          window.location.href = '/login?session=expired';
          return;
        }
      }

      throw err;
    }

    return json;
  }

  async function _silentRefresh() {
    const rt = Auth.getRefreshToken();
    if (!rt) return false;
    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!res.ok) return false;
      const json = await res.json();
      const d = json.data || json;
      if (d.access_token) {
        Auth.setSession(d.access_token, d.refresh_token || rt, null);
        return true;
      }
    } catch {}
    return false;
  }

  // ── Auth API ───────────────────────────────────────────────────
  const AuthAPI = {
    login: (email, password) =>
      request('POST', '/auth/login', { email, password }, { noAuth: true }),

    register: (email, password, first_name, last_name, role, department_id) =>
      request('POST', '/auth/register', { email, password, first_name, last_name, role: role || 'STUDENT', department_id }, { noAuth: true }),

    verifyEmail: (email, otp_code) =>
      request('POST', '/auth/verify-email', { email, otp_code }, { noAuth: true }),

    resendOtp: (email) =>
      request('POST', '/auth/resend-otp', { email }, { noAuth: true }),

    refresh: (refresh_token) =>
      request('POST', '/auth/refresh', { refresh_token }, { noAuth: true }),

    me: () =>
      request('GET', '/auth/me'),

    uploadResource: (formData) => {
      const token = Auth.getAccessToken();
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      return fetch(`${BASE_URL}/resources/upload`, {
        method: 'POST',
        headers,
        body: formData,
      }).then(async res => {
        let json;
        try { json = await res.json(); } catch {
          throw { type: 'PARSE_ERROR', message: 'Unexpected server response.' };
        }
        if (!res.ok) {
          throw { type: json.error?.code || 'UPLOAD_ERROR', message: json.error?.message || json.message || 'Upload failed' };
        }
        return json;
      });
    },
  };

  // ── Human-readable error messages ─────────────────────────────
  function friendlyError(err) {
    if (!err) return 'An unexpected error occurred.';
    if (typeof err === 'string') return err;
    const msg = err.message || '';
    const type = err.type || '';

    switch (type) {
      case 'NETWORK_ERROR':        return 'Connection error. Please check your internet.';
      case 'VALIDATION_ERROR':     return msg || 'Please check your input.';
      case 'UNAUTHORIZED':         return 'Incorrect email or password.';
      case 'USER_EXISTS':          return 'An account with this email already exists.';
      case 'INVALID_OTP':          return 'Incorrect verification code. Please try again.';
      case 'EXPIRED_OTP':          return 'Verification code has expired. Please request a new one.';
      case 'MAX_ATTEMPTS_EXCEEDED':return 'Too many failed attempts. Please request a new code.';
      case 'ACCOUNT_LOCKED':       return 'Account temporarily locked due to multiple failed attempts.';
      case 'EMAIL_NOT_VERIFIED':   return 'Please verify your email before logging in.';
    }

    if (err.status === 429) return 'Too many requests. Please wait a moment.';
    if (err.status === 500) return 'A server error occurred. Please try again.';
    return msg || 'Something went wrong. Please try again.';
  }

  // ── Route guard ────────────────────────────────────────────────
  const publicRoutes = ['/login', '/register', '/verify-email', '/forgot-password', '/reset-password', '/'];

  function enforceRouteGuard() {
    const path = window.location.pathname;
    const isAuth = Auth.isAuthenticated();

    // Authenticated user visiting public auth pages → redirect to dashboard
    if (isAuth && ['/login', '/register', '/verify-email', '/forgot-password', '/reset-password'].includes(path)) {
      const role = Auth.getRole();
      window.location.replace(dashboardForRole(role));
      return;
    }

    // Protected routes: if not authenticated → redirect to login
    const isPublic = publicRoutes.some(p => path === p || path.startsWith('/design-system'));
    if (!isAuth && !isPublic) {
      window.location.replace('/login?next=' + encodeURIComponent(window.location.pathname));
    }
  }

  // Expose to global
  global.CampusX = global.CampusX || {};
  global.CampusX.api = AuthAPI;
  global.CampusX.auth = Auth;
  global.CampusX.friendlyError = friendlyError;
  global.CampusX.dashboardForRole = dashboardForRole;
  global.CampusX.enforceRouteGuard = enforceRouteGuard;

})(window);
