import logging
import typing
from typing import Dict, Any
from sqlalchemy import select
from app.models.database import GameSession, Question, SessionPlayer, Player

if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class BotManager:
    def __init__(self, app: "Application"):
        self.app = app

    async def handle_update(self, update: Dict[str, Any]):
        try:
            if 'message' in update:
                await self._handle_message(update['message'])
        except Exception as e:
            logger.error(f"Error handling update: {e}")

    async def _handle_message(self, message: Dict[str, Any]):
        chat_id = message['chat']['id']
        text = message.get('text', '').strip()
        user_id = message['from']['id']
        username = message['from'].get('username', 'Unknown')

        if not text:
            return

        text_lower = text.lower()
        
        if text_lower in ['/start', 'начать игру', 'старт']:
            await self._handle_new_game(chat_id, user_id, username)
        elif text_lower == 'добавиться в игру':
            await self._handle_join_game(chat_id, user_id, username)
        elif text_lower in ['остановить игру', 'стоп']:
            await self._handle_stop_game(chat_id, user_id, username)
        elif text_lower == 'топ игроков':
            await self._handle_leaderboard(chat_id)
        elif text_lower == 'статус':
            await self._handle_status(chat_id)
        elif text_lower in ['начать сейчас', 'старт сейчас']:
            await self._handle_admin_start(chat_id, user_id, username)
        else:
            await self._handle_game_answer(chat_id, user_id, text)

    async def _handle_admin_start(self, chat_id: int, user_id: int, username: str):
        try:
            success, status = await self.app.store.game_accessor.admin_start_game(chat_id, user_id)
            
            if success:
                response = f"@{username} запустил игру принудительно!\n\n🎮 *Игра начинается!*"
            else:
                if status == "no_session":
                    response = "Нет активной игры в ожидании."
                elif status == "player_not_found":
                    response = "Игрок не найден."
                elif status == "not_admin":
                    response = "Только создатель игры может запустить ее принудительно."
                elif status == "not_enough_players":
                    response = "Недостаточно игроков для старта (минимум 2)."
                else:
                    response = "Не удалось запустить игру."
                    
        except Exception as e:
            logger.error(f"Error in admin start: {e}")
            response = "Произошла ошибка при запуске игры."

        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)

    async def _handle_new_game(self, chat_id: int, user_id: int, username: str):
        try:
            session = await self.app.store.game_accessor.create_session(chat_id, user_id)
            if session:
                response = (
                    f"*Игра '100 к 1' создана!*\n\n"
                    f"Создатель: @{username}\n"
                    f"Чтобы присоединиться, напишите: *'Добавиться в игру'*\n\n"
                    f"⚡ *Условия старта:*\n"
                    f"• Автоматически при 8 игроках\n"  
                    f"• Через 30 секунд (если есть 2+ игрока)\n"
                    f"• Принудительно: *'Старт сейчас'* (создатель)\n\n"
                    f"Таймер запущен!"
                )
            else:
                response = "❌ В этом чате уже есть активная игра! Дождитесь ее окончания."
        except Exception as e:
            logger.error(f"Error creating game: {e}")
            response = "❌ Произошла ошибка при создании игры."

        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)

    async def _handle_join_game(self, chat_id: int, user_id: int, username: str):
        try:
            success, status = await self.app.store.game_accessor.add_player_to_session(chat_id, user_id)
            
            if success:
                if status == "started":
                    response = f"@{username} присоединился к игре!\n\n🎮 *Игра начинается!* Смотрите вопрос выше 👆"
                else:
                    response = f"@{username} присоединился к игре! Ждем других игроков..."
            else:
                if status == "no_session":
                    response = "Нет активной игры в этом чате. Начните игру командой 'старт'"
                elif status == "already_joined":
                    response = f"@{username}, вы уже в игре!"
                else:
                    response = "Не удалось присоединиться к игре."
                    
        except Exception as e:
            logger.error(f"Error joining game: {e}")
            response = "Произошла ошибка при присоединении к игре."

        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)

    async def _handle_stop_game(self, chat_id: int, user_id: int, username: str):
        """Остановка игры"""
        try:
            success, status = await self.app.store.game_accessor.stop_game(chat_id, user_id)
            
            if success:
                response = f"@{username} остановил игру!\n\nИгра завершена."
            else:
                if status == "no_active_game":
                    response = "Нет активной игры для остановки."
                elif status == "player_not_found":
                    response = "Игрок не найден."
                elif status == "not_admin":
                    response = "Только создатель игры или администратор может остановить игру."
                else:
                    response = "Не удалось остановить игру."
                    
        except Exception as e:
            logger.error(f"Error stopping game: {e}")
            response = "Произошла ошибка при остановке игры."

        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)

    async def _handle_status(self, chat_id: int):
        try:
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers'])
                    ).order_by(GameSession.id.desc())
                )
                game_session_row = game_session_result.first()
                
                if not game_session_row:
                    response = "Нет активной игры в этом чате."
                else:
                    game_session = game_session_row[0]
                    
                    players_result = await session.execute(
                        select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
                    )
                    players_count = len(players_result.scalars().all())
                    
                    current_question = None
                    if game_session.current_question_id:
                        question_result = await session.execute(
                            select(Question).where(Question.id == game_session.current_question_id)
                        )
                        question_row = question_result.first()
                        if question_row:
                            current_question = question_row[0]
                    
                    response = (
                        f"*Статус игры:*\n"
                        f"• Состояние: {self._get_state_name(game_session.state)}\n"
                        f"• Игроков: {players_count}\n"
                        f"• Вопрос: {current_question.text if current_question else 'Еще не начат'}\n"
                        f"• Раунд: {game_session.current_question_round}"
                    )
                    
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            response = "Ошибка при получении статуса."

        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)

    def _get_state_name(self, state: str) -> str:
        states = {
            'waiting_players': 'Ожидание игроков',
            'question_start': 'Начало вопроса', 
            'accepting_answers': 'Прием ответов',
            'showing_results': 'Показ результатов',
            'finished': 'Завершена'
        }
        return states.get(state, state)

    async def _handle_leaderboard(self, chat_id: int):
        response = "Топ игроков будет доступен в следующем обновлении"
        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)

    async def _handle_game_answer(self, chat_id: int, user_id: int, answer_text: str):
        try:
            success = await self.app.store.game_accessor.submit_answer(chat_id, user_id, answer_text)
            if success:
                response = "Ответ принят! Ждем остальных игроков..."
            else:
                async with self.app.store.database.session() as session:
                    game_session_result = await session.execute(
                        select(GameSession).where(
                            GameSession.chat_id == chat_id,
                            GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers'])
                        ).order_by(GameSession.id.desc())
                    )
                    game_session_row = game_session_result.first()
                    
                    if not game_session_row:
                        response = "Сначала начните игру командой 'старт'"
                    else:
                        game_session = game_session_row[0]
                        if game_session.state != 'accepting_answers':
                            response = "Сейчас не время для ответов!"
                        else:
                            response = "Не удалось принять ответ. Возможно, вы уже ответили в этом раунде."
        except Exception as e:
            logger.error(f"Error submitting answer: {e}")
            response = "Произошла ошибка при отправке ответа."

        await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)