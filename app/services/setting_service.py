class SettingService:
    def get_settings(self, user_id: str = None):
        return {
            "theme": "lumina-dark",
            "notifications_enabled": True,
            "email_alerts": True
        }

    def update_settings(self, user_id: str, settings_data: dict):
        return settings_data
