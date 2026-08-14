from .base import BaseSchema, Schema, fields, validate, ValidationError

class SearchQuerySchema(Schema):
    query = fields.String(required=True)
    entity_type = fields.String() # e.g., 'user', 'course', 'resource'
    limit = fields.Integer(dump_default=10)
    offset = fields.Integer(dump_default=0)
