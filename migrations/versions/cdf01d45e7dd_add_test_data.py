"""add_test_data

Revision ID: cdf01d45e7dd
Revises: 724d44de98dd
Create Date: 2025-10-02 00:05:21.596367

"""

import sqlalchemy as sa
from sqlalchemy import column, table

from alembic import op

# revision identifiers
revision: str = "cdf01d45e7dd"
down_revision: str | None = "724d44de98dd"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade():
    # Создаем временные таблицы для вставки данных
    questions_table = table(
        "questions",
        column("id", sa.Integer),
        column("text", sa.String),
        column("is_active", sa.Boolean),
    )

    answer_variants_table = table(
        "answer_variants",
        column("id", sa.Integer),
        column("question_id", sa.Integer),
        column("text", sa.String),
        column("points", sa.Integer),
        column("position", sa.Integer),
    )

    # Вставляем тестовые вопросы (УБИРАЕМ РУЧНЫЕ ID)
    op.bulk_insert(
        questions_table,
        [
            {"text": "Что чаще всего ищут в интернете?", "is_active": True},
            {"text": "Что люди забывают дома?", "is_active": True},
            {"text": "Что берут с собой на море?", "is_active": True},
        ],
    )

    # Вставляем варианты ответов (УБИРАЕМ РУЧНЫЕ ID)
    op.bulk_insert(
        answer_variants_table,
        [
            # Вопрос 1
            {"question_id": 1, "text": "YouTube", "points": 40, "position": 1},
            {"question_id": 1, "text": "Google", "points": 30, "position": 2},
            {"question_id": 1, "text": "Погода", "points": 20, "position": 3},
            {"question_id": 1, "text": "Новости", "points": 10, "position": 4},
            {"question_id": 1, "text": "Карты", "points": 5, "position": 5},
            # Вопрос 2
            {"question_id": 2, "text": "Телефон", "points": 35, "position": 1},
            {"question_id": 2, "text": "Ключи", "points": 25, "position": 2},
            {"question_id": 2, "text": "Кошелек", "points": 20, "position": 3},
            {
                "question_id": 2,
                "text": "Документы",
                "points": 15,
                "position": 4,
            },
            {"question_id": 2, "text": "Очки", "points": 5, "position": 5},
            # Вопрос 3
            {
                "question_id": 3,
                "text": "Полотенце",
                "points": 30,
                "position": 1,
            },
            {
                "question_id": 3,
                "text": "Крем от загара",
                "points": 25,
                "position": 2,
            },
            {
                "question_id": 3,
                "text": "Купальник",
                "points": 20,
                "position": 3,
            },
            {"question_id": 3, "text": "Воду", "points": 15, "position": 4},
            {"question_id": 3, "text": "Очки", "points": 10, "position": 5},
        ],
    )


def downgrade():
    op.execute("DELETE FROM answer_variants")
    op.execute("DELETE FROM questions")
