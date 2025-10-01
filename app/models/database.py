from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class Player(Base):
    __tablename__ = "players"
    
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(30))
    rating = Column(Integer, default=1000)
    games_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    date_last_game = Column(DateTime)
    date_created_at = Column(DateTime, default=datetime.datetime.utcnow)

class GameSession(Base):
    __tablename__ = "game_sessions"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, nullable=False)  # that_id -> chat_id
    state = Column(String(15), default='waiting_players')
    total_questions = Column(Integer, default=5)
    current_question_number = Column(Integer, default=1)
    current_question_id = Column(Integer, ForeignKey('questions.id'))
    current_question_round = Column(Integer, default=1)  # раунды внутри вопроса

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True)
    text = Column(String(70), nullable=False)
    is_active = Column(Boolean, default=True)

class AnswerVariant(Base):
    __tablename__ = "answer_variants"
    
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    text = Column(String(20), nullable=False)
    points = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)  # 1-5 место

class SessionPlayer(Base):
    __tablename__ = "session_players"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    session_id = Column(Integer, ForeignKey('game_sessions.id'), nullable=False)
    is_admin = Column(Boolean, default=False)
    final_score = Column(Integer, default=0)
    final_position = Column(Integer)

class PlayerAnswer(Base):
    __tablename__ = "player_answers"
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    session_id = Column(Integer, ForeignKey('game_sessions.id'), nullable=False)
    round = Column(Integer, default=1)  # раунд внутри вопроса (1, 2, 3...)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    answer_text = Column(String(50), nullable=False)
    normalized_text = Column(String(50))
    points_earned = Column(Integer, default=0)