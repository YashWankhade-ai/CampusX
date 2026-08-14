from .base import BaseSchema, fields

class SettingsSchema(BaseSchema):
    theme = fields.String()
    notifications_enabled = fields.Boolean()
    email_alerts = fields.Boolean()
