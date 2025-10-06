import logging
import typing
from typing import Dict, Any
from sqlalchemy import select

from app.models.database import GameSession, SessionPlayer, Player

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
        try:
            chat_id = message['chat']['id']
            text = message.get('text', '').strip()
            user_id = message['from']['id']
            username = message['from'].get('username', 'Unknown')

            logger.info(f"Received message: '{text}' from user {user_id} in chat {chat_id}")  # ДОБАВЬ ЭТУ СТРОКУ

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
            elif text_lower == 'продолжить угадывать':
                logger.info("Processing 'продолжить угадывать' command")  # ДОБАВЬ ЭТУ СТРОКУ
                await self._handle_continue_guessing(chat_id, user_id, username)
            elif text_lower == 'следующий вопрос':
                logger.info("Processing 'следующий вопрос' command")  # ДОБАВЬ ЭТУ СТРОКУ
                await self._handle_next_question(chat_id, user_id, username)
            else:
                has_active_game = await self._check_active_game(chat_id)
                if has_active_game:
                    await self._handle_game_answer(chat_id, user_id, text, username)
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            try:
                chat_id = message['chat']['id']
                await self._send_error_message(chat_id, "Произошла ошибка при обработке команды")
            except:
                logger.error("Cannot send error message - no chat_id available")

    async def _handle_continue_guessing(self, chat_id: int, user_id: int, username: str):
        """Обработка команды 'Продолжить угадывать'"""
        try:
            logger.info(f"continue_guessing called for chat {chat_id} by user {user_id}")
            
            success = await self.app.store.game_accessor.continue_guessing(chat_id, user_id)
            
            if success:
                response = f"🔄 @{username} решил продолжить угадывать!\n\nНачинается следующий раунд!"
            else:
                response = "❌ Не удалось продолжить игру. Возможно, вы не создатель игры или игра не в нужном состоянии."
                
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error continuing game: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при продолжении игры")

    async def _handle_next_question(self, chat_id: int, user_id: int, username: str):
        """Обработка команды 'Следующий вопрос'"""
        try:
            logger.info(f"next_question called for chat {chat_id} by user {user_id}")
            
            success = await self.app.store.game_accessor.next_question(chat_id, user_id)
            
            if success:
                response = f"➡️ @{username} переходит к следующему вопросу!\n\nНовый вопрос начинается!"
            else:
                response = "❌ Не удалось перейти к следующему вопросу. Возможно, вы не создатель игры или игра завершена."
                
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error moving to next question: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при переходе к следующему вопросу")

    async def _check_active_game(self, chat_id: int) -> bool:
        try:
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(['question_start', 'accepting_answers'])
                    )
                )
                return game_session_result.first() is not None
        except Exception as e:
            logger.error(f"Error checking active game: {e}")
            return False

    async def _handle_new_game(self, chat_id: int, user_id: int, username: str):
        try:
            session = await self.app.store.game_accessor.create_session(chat_id, user_id, username)
            
            if session:
                response = (
                    f"Игра '100 к 1' создана!\n\n"
                    f"Создатель: @{username}\n"
                    f"Чтобы присоединиться, напишите: 'Добавиться в игру'\n\n"
                    f"Условия старта:\n"
                    f"Автоматически при 8 игроках\n"  
                    f"Через 60 секунд (если есть 2+ игрока)\n"
                    f"Принудительно: 'Старт сейчас' (создатель)\n\n"
                    f"Таймер запущен!"
                )
            else:
                response = "В этом чате уже есть активная игра! Дождитесь ее окончания."
                
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
            
        except Exception as e:
            logger.error(f"Error creating game: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при создании игры")

    async def _handle_join_game(self, chat_id: int, user_id: int, username: str):
        try:
            success, status = await self.app.store.game_accessor.add_player_to_session(chat_id, user_id, username)
            
            response_messages = {
                "auto_started": f"@{username} присоединился к игре!\n\nДостигнуто 8 игроков! Игра начинается!",
                "started": f"@{username} присоединился к игре!\n\nИгра начинается!",
                "joined": await self._get_players_count_message(chat_id, username),
                "no_session": "Нет активной игры в этом чате. Начните игру командой 'старт'",
                "already_joined": f"@{username}, вы уже в игре!"
            }
            
            response = response_messages.get(status, "Не удалось присоединиться к игре.")
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error joining game: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при присоединении к игре")

    async def _get_players_count_message(self, chat_id: int, username: str) -> str:
        try:
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
                    players_count_result = await session.execute(
                        select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
                    )
                    players_count = len(players_count_result.scalars().all())
                    return f"@{username} присоединился к игре! Игроков: {players_count}/8"
                else:
                    return f"@{username} присоединился к игре!"
        except Exception as e:
            logger.error(f"Error getting players count: {e}")
            return f"@{username} присоединился к игре!"

    async def _handle_admin_start(self, chat_id: int, user_id: int, username: str):
        try:
            success, status = await self.app.store.game_accessor.admin_start_game(chat_id, user_id)
            
            response_messages = {
                "started": f"@{username} запустил игру принудительно!\n\nИгра начинается!",
                "no_session": "Нет активной игры в ожидании.",
                "player_not_found": "Игрок не найден.",
                "not_admin": "Только создатель игры может запустить ее принудительно.",
                "not_enough_players": "Недостаточно игроков для старта (минимум 2).",
                "start_failed": "Не удалось запустить игру."
            }
            
            response = response_messages.get(status, "Не удалось запустить игру.")
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error in admin start: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при запуске игры")

    async def _handle_stop_game(self, chat_id: int, user_id: int, username: str):
        try:
            success, status = await self.app.store.game_accessor.stop_game(chat_id, user_id)
            
            response_messages = {
                "stopped": f"@{username} остановил игру!\n\nИгра завершена.",
                "no_active_game": "Нет активной игры для остановки.",
                "player_not_found": "Игрок не найден.",
                "not_admin": "Только создатель игры может остановить игру."
            }
            
            response = response_messages.get(status, "Не удалось остановить игру.")
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error stopping game: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при остановке игры")

    async def _handle_status(self, chat_id: int):
        try:
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers'])
                    )
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
                    
                    response = (
                        f"Статус игры:\n"
                        f"Состояние: {self._get_state_name(game_session.state)}\n"
                        f"Игроков: {players_count}\n"
                        f"Вопрос: {game_session.current_question_number}\n"
                        f"Раунд: {game_session.current_question_round}"
                    )
                    
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            await self._send_error_message(chat_id, "Ошибка при получении статуса")

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

    async def _handle_game_answer(self, chat_id: int, user_id: int, answer_text: str, username: str):
        try:
            success = await self.app.store.game_accessor.submit_answer(chat_id, user_id, answer_text)
            if success:
                response = "Ответ принят! Ждем остальных игроков..."
            else:
                response = "Не удалось принять ответ. Возможно, вы уже ответили в этом раунде."
                
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=response)
                    
        except Exception as e:
            logger.error(f"Error submitting answer: {e}")
            await self._send_error_message(chat_id, "Произошла ошибка при отправке ответа")

    async def _send_error_message(self, chat_id: int, message: str):
        """Универсальный метод для отправки сообщений об ошибках"""
        try:
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            logger.error(f"Error sending error message: {e}")