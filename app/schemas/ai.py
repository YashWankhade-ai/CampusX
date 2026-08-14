from .base import BaseSchema, Schema, fields, validate, ValidationError

class AIChatRequestSchema(Schema):
    message = fields.String(required=True)
    context = fields.Dict()
    
class AIInsightRequestSchema(Schema):
    student_id = fields.String(required=True)
    metric = fields.String()
