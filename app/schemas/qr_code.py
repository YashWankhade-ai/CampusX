from .base import BaseSchema, Schema, fields, validate, ValidationError

class QRCodeGenerateSchema(Schema):
    data = fields.String(required=True)
    size = fields.Integer(dump_default=200)

class QRCodeScanSchema(Schema):
    qr_data = fields.String(required=True)
    location = fields.String()
