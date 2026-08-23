"""Analytics Service — Sprint 10.

Business logic layer between API routes and analytics_repository.
All methods enforce institution isolation by deriving institution_id
from server-side JWT identity — never from client input.

Permissions (from ROLE_PERMISSIONS):
    analytics:read  → SUPER_ADMIN, INSTITUTION_ADMIN, MODERATOR, FACULTY
    analytics:export → SUPER_ADMIN, INSTITUTION_ADMIN

Personal statistics (any authenticated user — their own data only):
    GET /api/v1/analytics/me

Institution statistics (requires analytics:read permission):
    GET /api/v1/analytics/institution
"""
import logging
from typing import Optional, Dict, Any

from app.repositories import analytics_repository as repo

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Thin orchestration layer — delegates DB access to analytics_repository."""

    # ── Personal statistics ──────────────────────────────────────────────

    def get_personal_stats(self, user_id: str) -> Dict[str, Any]:
        """Return contribution statistics for the requesting user.

        Data is derived from real DB records — no hard-coded values.
        """
        uploads = repo.count_user_uploads(user_id)
        approved = repo.count_user_approved_uploads(user_id)
        approvals_given = repo.count_user_approvals_given(user_id)
        searches = repo.count_user_events(user_id, event_type="search.performed")

        return {
            "uploads_total": uploads,
            "uploads_approved": approved,
            "uploads_pending": max(0, uploads - approved),
            "approvals_given": approvals_given,
            "searches_performed": searches,
        }

    # ── Institution statistics ──────────────────────────────────────────

    def get_institution_stats(self, institution_id: str) -> Dict[str, Any]:
        """Return institution-scoped statistics.

        institution_id MUST come from JWT (server-side) — never from client.
        """
        event_counts = repo.count_events_by_type(institution_id=institution_id)
        approved = repo.count_approved_resources(institution_id=institution_id)
        pending = repo.count_pending_resources(institution_id=institution_id)

        return {
            "resources_approved": approved,
            "resources_pending": pending,
            "events": event_counts,
        }

    # ── Legacy stubs (used by old blueprint — replaced by routes below) ──

    def get_user_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Legacy alias for get_personal_stats."""
        return self.get_personal_stats(str(user_id))

    def get_platform_overview(self) -> Dict[str, Any]:
        """Platform-level aggregate (SUPER_ADMIN only)."""
        event_counts = repo.count_events_by_type()
        approved = repo.count_approved_resources()
        pending = repo.count_pending_resources()
        return {
            "resources_approved": approved,
            "resources_pending": pending,
            "events": event_counts,
        }

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Legacy alias used by old analytics_service callers."""
        return self.get_platform_overview()

    # ── Event recording helpers (called from upload/approval services) ──

    @staticmethod
    def record(
        event_type: str,
        user_id: Optional[str] = None,
        institution_id: Optional[str] = None,
        event_data: Optional[dict] = None,
    ) -> None:
        """Record an application event.

        Safe to call from any service — never raises.
        institution_id MUST come from server-side context, never client.
        """
        repo.record_event(
            event_type=event_type,
            user_id=user_id,
            institution_id=institution_id,
            event_data=event_data,
        )
