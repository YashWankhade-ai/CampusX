from app.models.contribution import Contribution, Badge
from app.extensions import db
from sqlalchemy import func
from datetime import datetime, timezone

class ContributionService:
    def calculate_points(self, user_id):
        total_points = db.session.query(func.sum(Contribution.points)).filter_by(user_id=user_id).scalar()
        return total_points or 0

    def add_contribution(self, user_id, action, points, resource_id=None):
        contribution = Contribution(
            user_id=user_id,
            action=action,
            points=points,
            resource_id=resource_id,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(contribution)
        db.session.commit()
        return contribution

    def award_badge(self, user_id, badge_name, badge_description, icon_url=None):
        badge = Badge(
            user_id=user_id,
            name=badge_name,
            description=badge_description,
            icon_url=icon_url,
            awarded_at=datetime.now(timezone.utc)
        )
        db.session.add(badge)
        db.session.commit()
        return badge

    def get_leaderboard(self, limit=10):
        leaderboard = db.session.query(
            Contribution.user_id,
            func.sum(Contribution.points).label('total_points')
        ).group_by(Contribution.user_id).order_by(func.sum(Contribution.points).desc()).limit(limit).all()
        
        return [{"user_id": row.user_id, "points": row.total_points} for row in leaderboard]
