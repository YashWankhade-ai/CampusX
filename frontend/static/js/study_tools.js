'use strict';
/**
 * CampusX Study Tools API Module
 * =================================
 * Exposes CampusX.studyTools.* for the three AI study-tool endpoints.
 *
 * Endpoints consumed:
 *   POST /api/v1/ai/quiz/generate
 *   POST /api/v1/ai/flashcards/generate
 *   POST /api/v1/ai/summarize
 *   GET  /api/v1/resources  (public — resource picker)
 *
 * Security contract:
 *   - institution_id ALWAYS from JWT (backend) — never sent by the client.
 *   - Bearer token read from CampusX.auth.getAccessToken().
 *   - resource_id sourced only from authenticated /api/v1/resources listing.
 *
 * Constants mirror backend app/services/ai/prompt_templates.py:
 *   MAX_QUIZ_QUESTIONS  = 15   (server clamps to [1, 15])
 *   MAX_FLASHCARD_COUNT = 20   (server clamps to [1, 20])
 */
(function () {
  if (!window.CampusX) window.CampusX = {};

  /* ── Backend-mirrored limits ────────────────────────────────────────────── */
  var MAX_QUIZ_QUESTIONS  = 15;
  var MAX_FLASHCARD_COUNT = 20;

  var API_BASE = '/api/v1';

  /* ── Internal helpers ───────────────────────────────────────────────────── */

  function _token() {
    if (window.CampusX && CampusX.auth && typeof CampusX.auth.getAccessToken === 'function') {
      var tok = CampusX.auth.getAccessToken();
      if (tok) return tok;
    }
    var match = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
    if (match) return decodeURIComponent(match[1]);
    return null;
  }

  async function _post(path, body) {
    var tok = _token();
    var headers = {
      'Content-Type': 'application/json',
    };
    if (tok) {
      headers['Authorization'] = 'Bearer ' + tok;
    }
    var res = await fetch(API_BASE + path, {
      method: 'POST',
      headers: headers,
      credentials: 'same-origin',
      body: JSON.stringify(body),
    });
    var json = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      var code = (json && json.error && json.error.code) ? json.error.code : '';
      var errType = res.status === 401 ? 'UNAUTHORIZED'
                  : res.status === 429 ? 'RATE_LIMITED'
                  : res.status === 404 ? 'NOT_FOUND'
                  : res.status === 422 ? 'UNPROCESSABLE'
                  : 'SERVER_ERROR';
      throw { type: errType, status: res.status, code: code, data: json };
    }
    return json;
  }

  async function _get(path) {
    var tok = _token();
    var headers = {};
    if (tok) {
      headers['Authorization'] = 'Bearer ' + tok;
    }
    var res = await fetch(API_BASE + path, {
      headers: headers,
      credentials: 'same-origin',
    });
    var json = await res.json().catch(function () { return {}; });
    if (!res.ok) throw { type: 'SERVER_ERROR', status: res.status, data: json };
    return json;
  }

  /* ── Public: human-readable error messages ──────────────────────────────── */

  function friendlyError(err) {
    if (!err) return 'Something went wrong. Please try again.';
    var code = err.code || ((err.data && err.data.error) ? err.data.error.code : '');
    var msg  = (err.data && err.data.error) ? err.data.error.message : '';
    if (err.type === 'UNAUTHORIZED') return 'Your session has expired. Please sign in again.';
    if (err.type === 'RATE_LIMITED') return 'Too many requests. Please wait a moment and try again.';
    if (err.type === 'NOT_FOUND' || code === 'NOT_FOUND') return 'This resource is no longer available.';
    if (code === 'NOT_APPROVED') return 'This resource has not been approved and cannot be used for study tools.';
    if (code === 'NO_CONTEXT') return 'There is not enough indexed content in this resource to generate study material. The document may not have been indexed yet.';
    if (err.type === 'UNPROCESSABLE') return msg || 'The resource could not be processed. Please try again.';
    if (typeof navigator !== 'undefined' && !navigator.onLine) return 'No internet connection. Please check your connection and try again.';
    return 'CampusX AI could not generate the study material. Please try again.';
  }

  /* ── Public: API calls ──────────────────────────────────────────────────── */

  async function generateQuiz(resourceId, numQuestions) {
    return _post('/ai/quiz/generate', {
      resource_id: resourceId,
      num_questions: numQuestions,
    });
  }

  async function generateFlashcards(resourceId, numCards) {
    return _post('/ai/flashcards/generate', {
      resource_id: resourceId,
      num_cards: numCards,
    });
  }

  async function generateSummary(resourceId) {
    return _post('/ai/summarize', { resource_id: resourceId });
  }

  async function listResources() {
    return _get('/resources?limit=100&sort_by=created_at');
  }

  /* ── Export ─────────────────────────────────────────────────────────────── */
  CampusX.studyTools = {
    MAX_QUIZ_QUESTIONS:  MAX_QUIZ_QUESTIONS,
    MAX_FLASHCARD_COUNT: MAX_FLASHCARD_COUNT,
    generateQuiz:       generateQuiz,
    generateFlashcards: generateFlashcards,
    generateSummary:    generateSummary,
    listResources:      listResources,
    friendlyError:      friendlyError,
  };

})();
