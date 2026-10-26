/**
 * CampusX Search Module — v1.0
 * Encapsulates all search + resource-discovery API calls.
 * Must be loaded after api.js (depends on CampusX.auth).
 *
 * Exposed on: CampusX.search.*
 *
 * Usage:
 *   CampusX.search.query({ q, page, limit, subject_id }) → Promise
 *   CampusX.search.autocomplete(q) → Promise
 *   CampusX.search.trending() → Promise
 *   CampusX.search.resource(id) → Promise
 *   CampusX.search.download(id) → Promise
 *   CampusX.search.bookmark(id) → Promise
 *   CampusX.search.debounce(fn, ms) → debounced function
 */

(function (global) {
  'use strict';

  const BASE = '/api/v1';

  function authHeader() {
    const token = global.CampusX && global.CampusX.auth ? global.CampusX.auth.getAccessToken() : null;
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  async function get(path) {
    let res;
    try {
      res = await fetch(BASE + path, { headers: authHeader() });
    } catch (_) {
      throw { type: 'NETWORK_ERROR', message: 'Connection error. Please check your internet.' };
    }

    if (res.status === 401) {
      // Let api.js silent-refresh logic handle it; surface as auth error
      throw { type: 'UNAUTHORIZED', message: 'Session expired. Please log in again.', status: 401 };
    }
    if (res.status === 403) {
      throw { type: 'FORBIDDEN', message: 'You do not have permission to perform this search.', status: 403 };
    }
    if (res.status === 503) {
      throw { type: 'UNAVAILABLE', message: 'Search is temporarily unavailable. Please try again.', status: 503 };
    }

    let json;
    try { json = await res.json(); } catch (_) {
      throw { type: 'PARSE_ERROR', message: 'Unexpected server response.' };
    }

    if (!res.ok) {
      throw { type: json.code || 'API_ERROR', message: json.message || 'An error occurred.', status: res.status };
    }

    return json;
  }

  async function post(path) {
    let res;
    try {
      res = await fetch(BASE + path, { method: 'POST', headers: authHeader() });
    } catch (_) {
      throw { type: 'NETWORK_ERROR', message: 'Connection error.' };
    }
    let json;
    try { json = await res.json(); } catch (_) { json = {}; }
    if (!res.ok) throw { type: json.code || 'API_ERROR', message: json.message || 'Error.', status: res.status };
    return json;
  }

  /**
   * Execute hybrid search.
   * @param {Object} opts - {q, page, limit, subject_id, department_id, semester_id}
   * @returns {Promise<{data: Array, meta: Object}>}
   */
  async function query(opts) {
    const params = new URLSearchParams();
    if (opts.q) params.set('q', opts.q);
    if (opts.page) params.set('page', String(opts.page));
    if (opts.limit) params.set('limit', String(opts.limit));
    if (opts.subject_id) params.set('subject_id', opts.subject_id);
    if (opts.department_id) params.set('department_id', opts.department_id);
    if (opts.semester_id) params.set('semester_id', opts.semester_id);
    return get('/search?' + params.toString());
  }

  /**
   * Fetch autocomplete suggestions.
   * @param {string} q - partial query string
   * @returns {Promise<string[]>}
   */
  async function autocomplete(q) {
    if (!q || q.length < 2) return [];
    const params = new URLSearchParams({ q });
    const res = await get('/search/autocomplete?' + params.toString());
    return Array.isArray(res.data) ? res.data : [];
  }

  /**
   * Fetch trending search topics.
   * @returns {Promise<Array<{topic: string, searches: number}>>}
   */
  async function trending() {
    const res = await get('/search/trending');
    return Array.isArray(res.data) ? res.data : [];
  }

  /**
   * Fetch resource metadata by ID.
   * @param {string} id
   * @returns {Promise<Object>}
   */
  async function resource(id) {
    const res = await get('/resources/' + id);
    return res.data || res;
  }

  /**
   * Get download URL for a resource.
   * @param {string} id
   * @returns {Promise<string>} download URL
   */
  async function download(id) {
    const res = await get('/resources/' + id + '/download');
    const url = (res.data && res.data.download_url) || res.download_url;
    if (!url) throw { type: 'NO_URL', message: 'Download link unavailable.' };
    return url;
  }

  /**
   * Toggle bookmark on a resource.
   * @param {string} id
   */
  async function bookmark(id) {
    return post('/resources/' + id + '/bookmark');
  }

  /**
   * Create a debounced function.
   * @param {Function} fn
   * @param {number} ms
   * @returns {Function}
   */
  function debounce(fn, ms) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  /**
   * Stale-guard: wrap an async function so that only the latest call's
   * result is accepted. Returns a function that takes the same args and
   * a callback(err, result).
   * @param {Function} asyncFn
   * @returns {Function}
   */
  function staleGuard(asyncFn) {
    let callId = 0;
    return async function (...args) {
      const id = ++callId;
      try {
        const result = await asyncFn(...args);
        if (id !== callId) return null; // stale — discard
        return result;
      } catch (err) {
        if (id !== callId) return null;
        throw err;
      }
    };
  }

  // Expose
  global.CampusX = global.CampusX || {};
  global.CampusX.search = { query, autocomplete, trending, resource, download, bookmark, debounce, staleGuard };

})(window);