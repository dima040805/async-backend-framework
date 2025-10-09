import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(String(100))
    rating: Mapped[int] = mapped_column(Integer, default=1000)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    date_last_game: Mapped[datetime.datetime | None] = mapped_column(
        DateTime
    )
    date_created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    session_players: Mapped[list["SessionPlayer"]] = relationship(
        back_populates="player"
    )
    answers: Mapped[list["PlayerAnswer"]] = relationship(
        back_populates="player"
    )


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(Text, default="waiting_players")
    total_questions: Mapped[int] = mapped_column(Integer, default=5)
    current_question_number: Mapped[int] = mapped_column(Integer, default=1)
    current_question_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("questions.id")
    )
    current_question_round: Mapped[int] = mapped_column(Integer, default=1)
    max_rounds_per_question: Mapped[int] = mapped_column(Integer, default=3)
    current_timer_id: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    current_question: Mapped[Optional["Question"]] = relationship("Question")
    session_players: Mapped[list["SessionPlayer"]] = relationship(
        back_populates="session"
    )
    answers: Mapped[list["PlayerAnswer"]] = relationship(
        back_populates="session"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    answer_variants: Mapped[list["AnswerVariant"]] = relationship(
        back_populates="question"
    )
    game_sessions: Mapped[list["GameSession"]] = relationship(
        back_populates="current_question"
    )


class AnswerVariant(Base):
    __tablename__ = "answer_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(100), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    question: Mapped["Question"] = relationship(
        back_populates="answer_variants"
    )


class SessionPlayer(Base):
    __tablename__ = "session_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_sessions.id"), nullable=False
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    final_score: Mapped[int] = mapped_column(Integer, default=0)
    final_position: Mapped[int | None] = mapped_column(Integer)
    joined_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    player: Mapped["Player"] = relationship(back_populates="session_players")
    session: Mapped["GameSession"] = relationship(
        back_populates="session_players"
    )


class PlayerAnswer(Base):
    __tablename__ = "player_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("game_sessions.id"), nullable=False
    )
    round: Mapped[int] = mapped_column(Integer, default=1)
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("questions.id"), nullable=False
    )
    answer_text: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(String(100))
    points_earned: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    player: Mapped["Player"] = relationship(back_populates="answers")
    session: Mapped["GameSession"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship("Question")
