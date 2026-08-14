from .base import BaseSchema, Schema, fields, validate, ValidationError

class AnalyticsRequestSchema(Schema):
    entity_type = fields.String(required=True)
    metric = fields.String(required=True)
    start_date = fields.Date()
    end_date = fields.Date()

class AnalyticsResponseSchema(Schema):
    entity_type = fields.String()
    metric = fields.String()
    data = fields.Dict()
