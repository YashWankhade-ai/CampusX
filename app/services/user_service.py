from app.models import User
from app.extensions import db

class UserService:
    def get_user_profile(self, user_id):
        return db.session.query(User).filter_by(id=user_id).first()

    def update_user_profile(self, user_id, **kwargs):
        user = self.get_user_profile(user_id)
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            db.session.commit()
        return user

    def assign_role(self, user_id, role):
        user = self.get_user_profile(user_id)
        if user:
            user.role = role
            db.session.commit()
        return user

    def list_users(self, limit=100, offset=0):
        return db.session.query(User).limit(limit).offset(offset).all()
