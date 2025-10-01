from marshmallow import Schema, fields


class AdminSchema(Schema):
    id = fields.Int()
    email = fields.Str()