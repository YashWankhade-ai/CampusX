from app.models.analytics import AnalyticsEvent
from app.extensions import db
from sqlalchemy import func
from datetime import datetime, timezone

class AnalyticsService:
    def record_analytics_event(self, user_id, event_type, resource_key=None, metadata=None):
        event = AnalyticsEvent(
            user_id=user_id,
            event_type=event_type,
            resource_key=resource_key,
            metadata_=metadata or {},
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(event)
        db.session.commit()
        return event

    def get_dashboard_metrics(self):
        total_events = db.session.query(func.count(AnalyticsEvent.id)).scalar()
        events_by_type = db.session.query(
            AnalyticsEvent.event_type, 
            func.count(AnalyticsEvent.id)
        ).group_by(AnalyticsEvent.event_type).all()
        
        active_users = db.session.query(func.count(func.distinct(AnalyticsEvent.user_id))).scalar()
        
        return {
            "total_events": total_events,
            "events_by_type": {e[0]: e[1] for e in events_by_type},
            "active_users": active_users
        }
