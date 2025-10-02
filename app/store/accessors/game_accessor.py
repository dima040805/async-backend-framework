import logging
import typing
from sqlalchemy import select
from app.store.database.base_accessor import BaseAccessor
from app.models.database import GameSession, Player, SessionPlayer, Question, AnswerVariant, PlayerAnswer
import asyncio 
from datetime import datetime, timedelta


if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class GameAccessor(BaseAccessor):
    def __init__(self, app: "Application"):
        super().__init__(app)
        self.active_sessions = {}


    async def create_session(self, chat_id: int, admin_telegram_id: int) -> GameSession:
        async with self.app.store.database.session() as session:
            # Проверяем: есть ли уже активная сессия в этом чате
            existing_session = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers'])
                )
            )
            if existing_session.first():
                return None  # Уже есть активная сессия

            # Находим или создаем игрока-админа
            player = await session.execute(
                select(Player).where(Player.telegram_id == admin_telegram_id)
            )
            player = player.scalar_one_or_none()
            
            if not player:
                player = Player(telegram_id=admin_telegram_id)
                session.add(player)
                await session.commit()

            # Создаем игровую сессию
            game_session = GameSession(
                chat_id=chat_id,
                state='waiting_players'
            )
            session.add(game_session)
            await session.commit()

            # Добавляем админа в сессию
            session_player = SessionPlayer(
                player_id=player.id,
                session_id=game_session.id,
                is_admin=True
            )
            session.add(session_player)
            await session.commit()

            self.active_sessions[chat_id] = game_session
            logger.info(f"Created game session {game_session.id} for chat {chat_id}")
            
            asyncio.create_task(self._auto_start_timer(chat_id, 30))
            
            return game_session

    async def _auto_start_timer(self, chat_id: int, duration: int):
        try:
            logger.info(f"⏰ Auto-start timer: {duration} seconds for chat {chat_id}")
            await asyncio.sleep(duration)
            
            # Проверяем что игра еще в состоянии ожидания
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == 'waiting_players'
                    )
                )
                game_session_row = game_session_result.first()
                
                if game_session_row:
                    game_session = game_session_row[0]
                    
                    # Проверяем количество игроков
                    players_count_result = await session.execute(
                        select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
                    )
                    players_count = len(players_count_result.scalars().all())
                    
                    if players_count >= 2:  # Стартуем если есть минимум 2 игрока
                        logger.info(f"Auto-start: Starting game in chat {chat_id} with {players_count} players")
                        await self.start_game(chat_id)
                        await self.app.store.telegram_api.send_message(
                            chat_id=chat_id, 
                            text="*Игра начинается автоматически!*"
                        )
                    else:
                        logger.info(f"Auto-start: Not enough players ({players_count}) in chat {chat_id}")
                        await self.app.store.telegram_api.send_message(
                            chat_id=chat_id, 
                            text="Время вышло! Недостаточно игроков для старта."
                        )
                        
        except Exception as e:
            logger.error(f"Error in auto-start timer: {e}")

    async def admin_start_game(self, chat_id: int, admin_telegram_id: int) -> bool:
        """Принудительный старт игры админом"""
        async with self.app.store.database.session() as session:
            # Находим сессию
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == 'waiting_players'
                )
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False, "no_session"
            
            game_session = game_session_row[0]

            # Проверяем права админа
            player_result = await session.execute(
                select(Player).where(Player.telegram_id == admin_telegram_id)
            )
            player = player_result.scalar_one_or_none()
            
            if not player:
                return False, "player_not_found"

            admin_check = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.player_id == player.id,
                    SessionPlayer.session_id == game_session.id,
                    SessionPlayer.is_admin == True
                )
            )
            
            if not admin_check.first():
                return False, "not_admin"

            # Проверяем количество игроков
            players_count_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players_count = len(players_count_result.scalars().all())
            
            if players_count < 2:
                return False, "not_enough_players"

            # Запускаем игру
            success = await self.start_game(chat_id)
            if success:
                return True, "started"
            else:
                return False, "start_failed"



    async def add_player_to_session(self, chat_id: int, telegram_id: int) -> tuple:
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == 'waiting_players'  # ТОЛЬКО waiting_players!
                ).order_by(GameSession.id.desc())
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False, "no_session"
            
            game_session = game_session_row[0]

            # Находим или создаем игрока
            player_result = await session.execute(
                select(Player).where(Player.telegram_id == telegram_id)
            )
            player = player_result.scalar_one_or_none()
            
            if not player:
                player = Player(telegram_id=telegram_id)
                session.add(player)
                await session.commit()
                player_result = await session.execute(
                    select(Player).where(Player.telegram_id == telegram_id)
                )
                player = player_result.scalar_one_or_none()

            # Проверяем, не добавлен ли уже игрок
            existing_player_result = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.player_id == player.id,
                    SessionPlayer.session_id == game_session.id
                )
            )
            existing_player = existing_player_result.first()
            
            if existing_player:
                return False, "already_joined"

            # Добавляем игрока в сессию
            session_player = SessionPlayer(
                player_id=player.id,
                session_id=game_session.id,
                is_admin=False
            )
            session.add(session_player)
            await session.commit()

            logger.info(f"Player {telegram_id} added to session {game_session.id}")

            players_count_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players_count = len(players_count_result.scalars().all())
            
            if players_count >= 8:  # Стартуем при 8 игроках
                start_success = await self.start_game(chat_id)
                if start_success:
                    return True, "auto_started"
            
            return True, "joined"

    
    async def start_game(self, chat_id: int) -> bool:
        """Запуск игры"""
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == 'waiting_players'
                )
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False
            
            game_session = game_session_row[0]

            # Получаем количество игроков
            players_count_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players_count = len(players_count_result.scalars().all())
            
            if players_count < 2:
                return False

            # Меняем состояние и начинаем игру
            game_session.state = 'question_start'
            await session.commit()

            # Получаем первый вопрос
            question_result = await session.execute(
                select(Question).where(Question.is_active == True).limit(1)
            )
            question_row = question_result.first()
            
            if question_row:
                question = question_row[0]
                game_session.current_question_id = question.id
                game_session.current_question_round = 1
                await session.commit()

                # ОТПРАВЛЯЕМ ВОПРОС В ЧАТ
                await self._send_question_to_chat(chat_id, question)
                
                # Меняем состояние на прием ответов
                game_session.state = 'accepting_answers'
                await session.commit()

                logger.info(f"Game started in chat {chat_id}")
                return True
            
            return False

    async def _send_question_to_chat(self, chat_id: int, question: Question):
        """Отправка вопроса в чат"""
        try:
            message = (
                f"*ВОПРОС №1:*\n"
                f"_{question.text}_\n\n"
                f"*Правила:*\n"
                f"• Присылайте свои ответы в чат\n"  
                f"• Каждый игрок может дать только 1 ответ\n"
                f"• Ответы принимаются 60 секунд\n\n"
                f"Время пошло!"
            )
            # Добавляем проверку что telegram_api существует
            if hasattr(self.app.store, 'telegram_api') and self.app.store.telegram_api:
                await self.app.store.telegram_api.send_message(chat_id=chat_id, text=message)
                logger.info(f"Question sent to chat {chat_id}")
            else:
                logger.error("Telegram API not available")
        except Exception as e:
            logger.error(f"Error sending question to chat: {e}")

    async def stop_game(self, chat_id: int, user_id: int) -> bool:
        """Остановка игры (только админ или создатель)"""
        async with self.app.store.database.session() as session:
            # Находим активную сессию
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers'])
                ).order_by(GameSession.id.desc())
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False, "no_active_game"
            
            game_session = game_session_row[0]

            # Проверяем права пользователя
            player_result = await session.execute(
                select(Player).where(Player.telegram_id == user_id)
            )
            player = player_result.scalar_one_or_none()
            
            if not player:
                return False, "player_not_found"

            # Проверяем является ли пользователь админом сессии
            admin_check = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.player_id == player.id,
                    SessionPlayer.session_id == game_session.id,
                    SessionPlayer.is_admin == True
                )
            )
            
            if not admin_check.first():
                return False, "not_admin"

            # Останавливаем игру
            game_session.state = 'finished'
            await session.commit()

            # Удаляем из активных сессий
            if chat_id in self.active_sessions:
                del self.active_sessions[chat_id]

            logger.info(f"Game stopped in chat {chat_id} by user {user_id}")
            return True, "stopped"
        

    async def submit_answer(self, chat_id: int, telegram_id: int, answer_text: str) -> bool:
        """Прием ответа от игрока"""
        async with self.app.store.database.session() as session:
            # Находим сессию и игрока
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == 'accepting_answers'
                )
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False
                
            game_session = game_session_row[0]
            
            player_result = await session.execute(
                select(Player).where(Player.telegram_id == telegram_id)
            )
            player = player_result.scalar_one_or_none()

            if not player:
                return False

            # Проверяем, не ответил ли уже игрок в этом раунде
            existing_answer = await session.execute(
                select(PlayerAnswer).where(
                    PlayerAnswer.player_id == player.id,
                    PlayerAnswer.session_id == game_session.id,
                    PlayerAnswer.round == game_session.current_question_round
                )
            )
            if existing_answer.first():
                return False

            # Сохраняем ответ
            player_answer = PlayerAnswer(
                player_id=player.id,
                session_id=game_session.id,
                question_id=game_session.current_question_id,
                round=game_session.current_question_round,
                answer_text=answer_text,
                normalized_text=answer_text.lower().strip()
            )
            session.add(player_answer)
            await session.commit()

            logger.info(f"Answer submitted by {telegram_id} in chat {chat_id}")
            return True