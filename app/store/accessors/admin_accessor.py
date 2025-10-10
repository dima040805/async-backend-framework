import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound

from app.models.database import (
    GameSession,
    Player,
    Question,
    SessionAdmin,
    SessionPlayer,
    WebAdmin,
)
from app.store.database.base_accessor import BaseAccessor

logger = logging.getLogger(__name__)


class AdminAccessor(BaseAccessor):
    async def authenticate_admin(self, email: str, password: str) -> Optional[WebAdmin]:
        """Аутентификация веб-админа"""
        try:
            async with self.app.store.database.session() as session:
                result = await session.execute(
                    select(WebAdmin).where(
                        WebAdmin.email == email,
                        WebAdmin.is_active == True
                    )
                )
                admin = result.scalar_one_or_none()
                
                if admin and self._verify_password(password, admin.password_hash):
                    return admin
                return None
                
        except Exception:
            logger.exception("Error authenticating admin")
            return None

    async def get_admin_by_id(self, admin_id: int) -> Optional[WebAdmin]:
        """Получить админа по ID"""
        async with self.app.store.database.session() as session:
            result = await session.execute(
                select(WebAdmin).where(WebAdmin.id == admin_id)
            )
            return result.scalar_one_or_none()

    async def create_web_admin(self, email: str, password: str) -> Optional[WebAdmin]:
        """Создать нового веб-админа"""
        try:
            async with self.app.store.database.session() as session:
                admin = WebAdmin(
                    email=email,
                    password_hash=self._hash_password(password),
                    is_active=True,
                    permissions="admin"
                )
                session.add(admin)
                await session.commit()
                await session.refresh(admin)
                return admin
        except Exception:
            logger.exception("Error creating admin")
            return None

    async def get_all_game_sessions(self, limit: int = 50, offset: int = 0) -> List[GameSession]:
        """Получить все игровые сессии"""
        async with self.app.store.database.session() as session:
            result = await session.execute(
                select(GameSession)
                .order_by(GameSession.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()

    async def get_active_sessions(self) -> List[GameSession]:
        """Получить активные сессии"""
        async with self.app.store.database.session() as session:
            result = await session.execute(
                select(GameSession).where(
                    GameSession.state.in_([
                        "waiting_players", 
                        "question_start", 
                        "accepting_answers",
                        "showing_results", 
                        "round_transition"
                    ])
                )
            )
            return result.scalars().all()

    async def get_session_players_count(self, session_id: int) -> int:
        """Получить количество игроков в сессии"""
        async with self.app.store.database.session() as session:
            result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == session_id)
            )
            return len(result.scalars().all())

    async def get_top_players(self, limit: int = 100) -> List[Player]:
        """Получить топ игроков"""
        async with self.app.store.database.session() as session:
            result = await session.execute(
                select(Player)
                .where(Player.games_played > 0)
                .order_by(Player.total_points.desc())
                .limit(limit)
            )
            return result.scalars().all()

    async def get_all_questions(self) -> List[Question]:
        """Получить все вопросы"""
        async with self.app.store.database.session() as session:
            result = await session.execute(
                select(Question).order_by(Question.id)
            )
            return result.scalars().all()

    async def create_question(self, text: str, is_active: bool = True) -> Optional[Question]:
        """Создать новый вопрос"""
        try:
            async with self.app.store.database.session() as session:
                question = Question(text=text, is_active=is_active)
                session.add(question)
                await session.commit()
                await session.refresh(question)
                return question
        except Exception:
            logger.exception("Error creating question")
            return None

    async def update_question_status(self, question_id: int, is_active: bool) -> bool:
        """Обновить статус вопроса"""
        try:
            async with self.app.store.database.session() as session:
                result = await session.execute(
                    select(Question).where(Question.id == question_id)
                )
                question = result.scalar_one_or_none()
                
                if question:
                    question.is_active = is_active
                    await session.commit()
                    return True
                return False
        except Exception:
            logger.exception("Error updating question")
            return False

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля (упрощенная версия)"""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        return self._hash_password(password) == password_hash   