from app.models.notification import Notification
from app.models import User
from app.extensions import db
from datetime import datetime, timezone

class NotificationService:
    def send_notification(self, user_id, title, message, notification_type='info'):
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=notification_type,
            is_read=False,
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(notification)
        db.session.commit()
        return notification

    def broadcast_notification(self, title, message, notification_type='info'):
        users = db.session.query(User).all()
        notifications = []
        for user in users:
            notifications.append(Notification(
                user_id=user.id,
                title=title,
                message=message,
                type=notification_type,
                is_read=False,
                created_at=datetime.now(timezone.utc)
            ))
        db.session.add_all(notifications)
        db.session.commit()
        return len(notifications)

    def get_user_notifications(self, user_id, unread_only=False):
        query = db.session.query(Notification).filter_by(user_id=user_id)
        if unread_only:
            query = query.filter_by(is_read=False)
        return query.order_by(Notification.created_at.desc()).all()

    def mark_read(self, notification_id, user_id):
        notification = db.session.query(Notification).filter_by(id=notification_id, user_id=user_id).first()
        if notification:
            notification.is_read = True
            db.session.commit()
            return True
        return False
