"""Add 100k1 game tables

Revision ID: 724d44de98dd
Revises: 030b61fc41c4
Create Date: 2025-10-01 17:47:10.110966

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "724d44de98dd"
down_revision: str | None = "030b61fc41c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "web_admins",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("permissions", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "admins",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("is_super_admin", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "game_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scheduled_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("execute_at", sa.DateTime(), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=True),
        sa.Column("is_completed", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["game_sessions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "game_sessions", sa.Column("created_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "game_sessions", sa.Column("updated_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "player_answers", sa.Column("created_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "session_players", sa.Column("joined_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("session_players", "joined_at")
    op.drop_column("player_answers", "created_at")
    op.drop_column("game_sessions", "updated_at")
    op.drop_column("game_sessions", "created_at")
    op.drop_table("scheduled_events")
    op.drop_table("game_states")
    op.drop_table("admins")
    op.drop_table("web_admins")