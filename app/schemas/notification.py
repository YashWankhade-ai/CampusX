from .base import BaseSchema, Schema, fields, validate, ValidationError

class NotificationSchema(BaseSchema):
    user_id = fields.String(required=True)
    title = fields.String(required=True)
    message = fields.String(required=True)
    is_read = fields.Boolean(dump_default=False)
    notification_type = fields.String(validate=validate.OneOf(["SYSTEM", "ALERT", "MESSAGE"]))

class NotificationCreateSchema(Schema):
    user_id = fields.String(required=True)
    title = fields.String(required=True)
    message = fields.String(required=True)
    notification_type = fields.String(validate=validate.OneOf(["SYSTEM", "ALERT", "MESSAGE"]))
