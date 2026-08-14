from .base import BaseSchema, Schema, fields, validate, ValidationError

class UserSchema(BaseSchema):
    email = fields.Email(required=True)
    username = fields.String(required=True, validate=validate.Length(min=3, max=50))
    first_name = fields.String(required=True)
    last_name = fields.String(required=True)
    role = fields.String(validate=validate.OneOf([
        "SUPER_ADMIN", "ADMIN", "FACULTY", "DEPARTMENT_COORDINATOR", "LIBRARIAN", "STUDENT"
    ]))
    is_active = fields.Boolean(dump_only=True)

class UserCreateSchema(UserSchema):
    password = fields.String(required=True, load_only=True, validate=validate.Length(min=8))

UserResponseSchema = UserSchema

class UserUpdateSchema(BaseSchema):
    first_name = fields.String()
    last_name = fields.String()
    is_active = fields.Boolean()
