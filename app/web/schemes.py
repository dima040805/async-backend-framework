from marshmallow import Schema, fields


class OkResponseSchema(Schema):
    status = fields.Str(required=True)
    data = fields.Dict(required=True)