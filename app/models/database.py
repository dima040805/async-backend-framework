import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Player(Base):
    __tablename__ = "players"
    
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)  # ✅ Должно быть BigInteger
    username = Column(String(30))
    rating = Column(Integer, default=1000)
    games_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    date_last_game = Column(DateTime)
    date_created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Связи
    admin_roles = relationship("Admin", back_populates="player")
    session_players = relationship("SessionPlayer", back_populates="player")
    answers = relationship("PlayerAnswer", back_populates="player")



class GameSession(Base):
    __tablename__ = "game_sessions"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, nullable=False)  
    state = Column(String(15), default='waiting_players')
    total_questions = Column(Integer, default=5)
    current_question_number = Column(Integer, default=1)
    current_question_id = Column(Integer, ForeignKey('questions.id'))
    current_question_round = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Связи
    current_question = relationship("Question")
    admins = relationship("Admin", back_populates="session")
    session_players = relationship("SessionPlayer", back_populates="session")
    answers = relationship("PlayerAnswer", back_populates="session")
    game_state = relationship(
        "GameState", back_populates="session", uselist=False
    )
    scheduled_events = relationship("ScheduledEvent", back_populates="session")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    text = Column(String(70), nullable=False)
    is_active = Column(Boolean, default=True)

    # Связи
    answer_variants = relationship("AnswerVariant", back_populates="question")
    game_sessions = relationship(
        "GameSession", back_populates="current_question"
    )
    answers = relationship("PlayerAnswer", back_populates="question")


class AnswerVariant(Base):
    __tablename__ = "answer_variants"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    text = Column(String(20), nullable=False)
    points = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)

    # Связи
    question = relationship("Question", back_populates="answer_variants")


class SessionPlayer(Base):
    __tablename__ = "session_players"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    is_admin = Column(Boolean, default=False)
    final_score = Column(Integer, default=0)
    final_position = Column(Integer)
    joined_at = Column(DateTime, default=datetime.datetime.utcnow)

    player = relationship("Player", back_populates="session_players")
    session = relationship("GameSession", back_populates="session_players")


class PlayerAnswer(Base):
    __tablename__ = "player_answers"

    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    round = Column(Integer, default=1)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text = Column(String(50), nullable=False)
    normalized_text = Column(String(50))
    points_earned = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    player = relationship("Player", back_populates="answers")
    session = relationship("GameSession", back_populates="answers")
    question = relationship("Question", back_populates="answers")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(BigInteger, primary_key=True)
    player_id = Column(BigInteger, ForeignKey("players.id"), nullable=False)
    session_id = Column(
        BigInteger, ForeignKey("game_sessions.id"), nullable=False
    )
    is_super_admin = Column(Boolean, default=False)

    player = relationship("Player", back_populates="admin_roles")
    session = relationship("GameSession", back_populates="admins")


class WebAdmin(Base):
    __tablename__ = "web_admins"

    id = Column(BigInteger, primary_key=True)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    permissions = Column(String(50), default="viewer")


class GameState(Base):
    __tablename__ = "game_states"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    state_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    session = relationship("GameSession", back_populates="game_state")


class ScheduledEvent(Base):
    __tablename__ = "scheduled_events"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    execute_at = Column(DateTime, nullable=False)
    event_data = Column(JSON)
    is_completed = Column(Boolean, default=False)

    session = relationship("GameSession", back_populates="scheduled_events")
