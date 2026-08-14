from datetime import datetime

try:
    from marshmallow import Schema, fields, pre_load, post_dump, validate, ValidationError
except ImportError:
    class Schema:
        def load(self, data): return data
        def dump(self, obj): return obj
    class _Fields:
        def String(self, *a, **k): return None
        def Email(self, *a, **k): return None
        def DateTime(self, *a, **k): return None
        def Date(self, *a, **k): return None
        def Time(self, *a, **k): return None
        def UUID(self, *a, **k): return None
        def Number(self, *a, **k): return None
        def Field(self, *a, **k): return None
        def Method(self, *a, **k): return None
        def Function(self, *a, **k): return None
        def Boolean(self, *a, **k): return None
        def Integer(self, *a, **k): return None
        def Float(self, *a, **k): return None
        def Nested(self, *a, **k): return None
        def List(self, *a, **k): return None
        def Dict(self, *a, **k): return None
    fields = _Fields()
    pre_load = post_dump = lambda f: f
    class validate:
        @staticmethod
        def Length(*a, **k): return None
        @staticmethod
        def OneOf(*a, **k): return None
        @staticmethod
        def Range(*a, **k): return None
        @staticmethod
        def Equal(*a, **k): return None
    class ValidationError(Exception):
        def __init__(self, messages):
            self.messages = messages

class BaseSchema(Schema):
    id = fields.String(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    class Meta:
        ordered = True
