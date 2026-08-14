from .base import BaseSchema, Schema, fields, validate, ValidationError

class ApprovalSchema(BaseSchema):
    request_type = fields.String(required=True)
    requester_id = fields.String(required=True)
    status = fields.String(validate=validate.OneOf(["PENDING", "APPROVED", "REJECTED"]))
    details = fields.Dict()

class ApprovalCreateSchema(BaseSchema):
    request_type = fields.String(required=True)
    details = fields.Dict(required=True)

class ApprovalActionSchema(BaseSchema):
    action = fields.String(required=True, validate=validate.OneOf(["APPROVE", "REJECT"]))
    reason = fields.String()
