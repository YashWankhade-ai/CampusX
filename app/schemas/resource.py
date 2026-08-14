from .base import BaseSchema, Schema, fields, validate, ValidationError

class ResourceSchema(BaseSchema):
    title = fields.String(required=True)
    description = fields.String()
    resource_type = fields.String(required=True, validate=validate.OneOf(["NOTE", "QUESTION_PAPER", "SYLLABUS", "ASSIGNMENT"]))
    status = fields.String(validate=validate.OneOf(["PENDING", "APPROVED", "REJECTED"]))

class ResourceCreateSchema(ResourceSchema):
    pass

ResourceUploadSchema = ResourceCreateSchema
ResourceResponseSchema = ResourceSchema

class ResourceUpdateSchema(BaseSchema):
    title = fields.String()
    description = fields.String()
    status = fields.String(validate=validate.OneOf(["PENDING", "APPROVED", "REJECTED"]))
