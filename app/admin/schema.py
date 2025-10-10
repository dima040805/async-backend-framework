from marshmallow import Schema, fields, validate


class AdminLoginSchema(Schema):
    email = fields.Str(required=True, validate=validate.Email())
    password = fields.Str(required=True)


class AdminResponseSchema(Schema):
    id = fields.Int(required=True)
    email = fields.Str(required=True)
    permissions = fields.Str(required=True)
    is_active = fields.Bool(required=True)


class QuestionSchema(Schema):
    id = fields.Int(required=True)
    text = fields.Str(required=True)
    is_active = fields.Bool(required=True)


class QuestionCreateSchema(Schema):
    text = fields.Str(required=True, validate=validate.Length(min=5, max=255))
    is_active = fields.Bool(missing=True)


class AnswerVariantSchema(Schema):
    id = fields.Int(required=True)
    text = fields.Str(required=True)
    points = fields.Int(required=True)
    position = fields.Int(required=True)


class AnswerVariantCreateSchema(Schema):
    text = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    points = fields.Int(required=True, validate=validate.Range(min=1, max=100))
    position = fields.Int(required=True, validate=validate.Range(min=1, max=10))


class GameSessionSchema(Schema):
    id = fields.Int(required=True)
    chat_id = fields.Int(required=True)
    state = fields.Str(required=True)
    total_questions = fields.Int(required=True)
    current_question_number = fields.Int(required=True)
    players_count = fields.Int(required=True)
    created_at = fields.DateTime(required=True)


class PlayerStatsSchema(Schema):
    id = fields.Int(required=True)
    telegram_id = fields.Int(required=True)
    username = fields.Str(required=True)
    games_played = fields.Int(required=True)
    wins = fields.Int(required=True)
    total_points = fields.Int(required=True)
    rating = fields.Int(required=True)


class SessionListSchema(Schema):
    amount = fields.Int(required=True)
    sessions = fields.Nested(GameSessionSchema, many=True)


class PlayerListSchema(Schema):
    amount = fields.Int(required=True)
    players = fields.Nested(PlayerStatsSchema, many=True)


class QuestionListSchema(Schema):
    amount = fields.Int(required=True)
    questions = fields.Nested(QuestionSchema, many=True)
