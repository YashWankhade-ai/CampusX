from .base import BaseSchema, Schema, fields, validate, ValidationError

class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=8))
    first_name = fields.String(required=True)
    last_name = fields.String(required=True)
    role = fields.String(required=False)

class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True)

class TokenRefreshSchema(Schema):
    refresh_token = fields.String(required=True)

class ChangePasswordSchema(Schema):
    old_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=8))

class ResetPasswordSchema(Schema):
    token = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=8))
