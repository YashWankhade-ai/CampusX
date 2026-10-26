/**
 * CampusX AI Module — v1.0
 * Wraps all AI-related API calls.
 * Must be loaded after api.js (depends on CampusX.auth).
 * Exposed on: CampusX.ai.*
 *
 * Backend contract:
 *   POST /api/v1/ai/ask
 *   POST /api/v1/ai/pdf/sessions  (single-PDF: {resource_id} | multi-PDF: {resource_ids:[]})
 *   POST /api/v1/ai/pdf/chat      {session_id, message}
 *   GET  /api/v1/ai/pdf/sessions/<id>
 *   GET  /api/v1/resources        (public — for resource picker)
 *   GET  /api/v1/search?q=        (authed — for resource picker search)
 *
 * Never exposes institution_id — always comes from JWT on the server.
 */

(function (global) {
  'use strict';

  const BASE = '/api/v1';

  /** Maximum characters per AI query — mirrors backend MAX_QUERY_LEN */
  const MAX_QUERY_LEN = 2000;

  /** Maximum resources per Multi-PDF session — mirrors backend _MAX_MULTI_PDF */
  const MAX_MULTI_PDF = 10;

  function authHeader() {
    let token = global.CampusX && global.CampusX.auth
      ? global.CampusX.auth.getAccessToken() : null;
    if (!token) {
      const match = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
      if (match) token = decodeURIComponent(match[1]);
    }
    return token ? { Authorization: 'Bearer ' + token } : {};
  }

  async function post(path, body) {
    let res;
    try {
      res = await fetch(BASE + path, {
        method: 'POST',
        headers: { ...authHeader(), 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body),
      });
    } catch (_) {
      throw { type: 'NETWORK_ERROR', message: 'Connection error. Please check your internet connection.' };
    }
    return _handleResponse(res);
  }

  async function get(path) {
    let res;
    try {
      res = await fetch(BASE + path, {
        headers: authHeader(),
        credentials: 'same-origin',
      });
    } catch (_) {
      throw { type: 'NETWORK_ERROR', message: 'Connection error.' };
    }
    return _handleResponse(res);
  }

  async function _handleResponse(res) {
    let json;
    try { json = await res.json(); } catch (_) {
      throw { type: 'PARSE_ERROR', message: 'Unexpected server response.' };
    }

    if (res.status === 401) {
      throw { type: 'UNAUTHORIZED', message: 'Your session has expired. Please sign in again.', status: 401, json };
    }
    if (res.status === 403) {
      throw { type: 'FORBIDDEN', message: 'You do not have permission to use CampusX AI.', status: 403, json };
    }
    if (res.status === 404) {
      throw { type: 'NOT_FOUND', message: 'Resource not found.', status: 404, json };
    }
    if (res.status === 422) {
      const msg = json.message || 'This resource is not available for AI chat.';
      throw { type: json.code || 'UNPROCESSABLE', message: msg, status: 422, json };
    }
    if (res.status === 429) {
      throw { type: 'RATE_LIMITED', message: 'Too many requests. Please wait a moment and try again.', status: 429, json };
    }
    if (res.status === 503) {
      throw { type: 'AI_UNAVAILABLE', message: 'CampusX AI is temporarily unavailable. Please try again.', status: 503, json };
    }
    if (!res.ok) {
      const msg = json.message || 'CampusX AI is temporarily unavailable. Please try again.';
      throw { type: json.code || 'AI_ERROR', message: msg, status: res.status, json };
    }
    return json;
  }

  /**
   * General Q&A — POST /api/v1/ai/ask
   * @param {string} query
   * @param {string|null} subjectId  optional
   * @returns {Promise<{answer, session_id, citations, confidence, confidence_score,
   *                    confidence_level, grounding_status, model_used}>}
   */
  async function ask(query, subjectId) {
    if (!query || !query.trim()) throw { type: 'VALIDATION_ERROR', message: 'Query cannot be empty.' };
    if (query.length > MAX_QUERY_LEN) throw { type: 'VALIDATION_ERROR', message: `Query too long (max ${MAX_QUERY_LEN} chars).` };
    const body = { query: query.trim() };
    if (subjectId) body.subject_id = subjectId;
    const res = await post('/ai/ask', body);
    return res.data || res;
  }

  /**
   * Create a single-PDF chat session — POST /api/v1/ai/pdf/sessions
   * @param {string} resourceId
   * @returns {Promise<{session_id, session_type, resource_id, resource_title, title}>}
   */
  async function createPdfSession(resourceId) {
    const res = await post('/ai/pdf/sessions', { resource_id: resourceId });
    return res.data || res;
  }

  /**
   * Create a Multi-PDF chat session — POST /api/v1/ai/pdf/sessions
   * @param {string[]} resourceIds  1–MAX_MULTI_PDF resource IDs
   * @returns {Promise<{session_id, session_type, resource_ids, resource_count, title}>}
   */
  async function createMultiPdfSession(resourceIds) {
    if (!Array.isArray(resourceIds) || resourceIds.length === 0) {
      throw { type: 'VALIDATION_ERROR', message: 'Select at least one resource.' };
    }
    if (resourceIds.length > MAX_MULTI_PDF) {
      throw { type: 'VALIDATION_ERROR', message: `Maximum ${MAX_MULTI_PDF} resources per session.` };
    }
    const res = await post('/ai/pdf/sessions', { resource_ids: resourceIds });
    return res.data || res;
  }

  /**
   * Send a message in a PDF chat session — POST /api/v1/ai/pdf/chat
   * @param {string} sessionId
   * @param {string} message
   * @returns {Promise<{session_id, response, citations, confidence, confidence_score,
   *                    confidence_level, grounding_status, resource_id|resource_ids}>}
   */
  async function pdfChat(sessionId, message) {
    if (!sessionId) throw { type: 'VALIDATION_ERROR', message: 'Session ID required.' };
    if (!message || !message.trim()) throw { type: 'VALIDATION_ERROR', message: 'Message cannot be empty.' };
    if (message.length > MAX_QUERY_LEN) throw { type: 'VALIDATION_ERROR', message: `Message too long (max ${MAX_QUERY_LEN} chars).` };
    const res = await post('/ai/pdf/chat', { session_id: sessionId, message: message.trim() });
    return res.data || res;
  }

  /**
   * Get PDF session history — GET /api/v1/ai/pdf/sessions/<id>
   * @param {string} sessionId
   * @returns {Promise<{session_id, title, resource_id, resource_title, resource_ids,
   *                    session_type, created_at, messages[]}>}
   */
  async function getPdfSession(sessionId) {
    const res = await get('/ai/pdf/sessions/' + encodeURIComponent(sessionId));
    return res.data || res;
  }

  /**
   * Fetch resources for the resource picker — GET /api/v1/resources
   * Uses public endpoint; no auth needed.
   * @param {Object} opts  {page, limit, search}
   * @returns {Promise<{data:[], meta:{}}>}
   */
  async function listResources(opts) {
    const params = new URLSearchParams();
    if (opts && opts.page) params.set('page', String(opts.page));
    if (opts && opts.limit) params.set('limit', String(opts.limit));
    if (opts && opts.search) params.set('search', opts.search);
    const q = params.toString();
    const res = await get('/resources' + (q ? '?' + q : ''));
    return res;
  }

  /**
   * Search resources for the resource picker — GET /api/v1/search
   * Requires auth + search:use permission.
   * @param {string} query
   * @returns {Promise<{data:[], meta:{}}>}
   */
  async function searchResources(query) {
    if (!query || query.length < 2) return { data: [], meta: {} };
    const params = new URLSearchParams({ q: query, limit: '20' });
    const res = await get('/search?' + params.toString());
    return res;
  }

  /**
   * Human-readable error message for AI errors.
   * @param {Object} err  error thrown by this module
   * @returns {string}
   */
  function friendlyError(err) {
    if (!err) return 'An unexpected error occurred. Please try again.';
    if (err.type === 'NETWORK_ERROR') return err.message || 'Connection error. Please check your internet.';
    if (err.type === 'UNAUTHORIZED') return err.message || 'Session expired. Please sign in again.';
    if (err.type === 'FORBIDDEN') return 'You do not have permission to use CampusX AI.';
    if (err.type === 'NOT_FOUND') return 'The resource was not found or is no longer available.';
    if (err.type === 'NOT_APPROVED') return 'This resource has not been approved and cannot be used for AI chat.';
    if (err.type === 'RATE_LIMITED') return 'Too many requests. Please wait a moment and try again.';
    if (err.type === 'AI_UNAVAILABLE') return 'CampusX AI is temporarily unavailable. Please try again shortly.';
    if (err.type === 'VALIDATION_ERROR') return err.message || 'Invalid input.';
    return err.message || 'CampusX AI encountered an issue. Please try again.';
  }

  // Expose
  global.CampusX = global.CampusX || {};
  global.CampusX.ai = {
    MAX_QUERY_LEN,
    MAX_MULTI_PDF,
    ask,
    createPdfSession,
    createMultiPdfSession,
    pdfChat,
    getPdfSession,
    listResources,
    searchResources,
    friendlyError,
  };

})(window);
