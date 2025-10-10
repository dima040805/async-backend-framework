import logging
import typing
from typing import Any

from sqlalchemy import select

from app.models.database import GameSession, SessionPlayer

if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class BotManager:
    def __init__(self, app: "Application"):
        self.app = app

    async def handle_update(self, update: dict[str, Any]):
        try:
            logger.info("Received update: %s", update.get("update_id"))

            if "message" in update:
                await self._handle_message(update["message"])
            elif "callback_query" in update:
                await self._handle_callback_query(update["callback_query"])

        except Exception:
            logger.exception("Error handling update")

    async def _handle_callback_query(self, callback_query: dict[str, Any]):
        chat_id = callback_query["message"]["chat"]["id"]
        user_id = callback_query["from"]["id"]
        username = callback_query["from"].get("username", "Unknown")
        data = callback_query["data"]

        logger.info(
            "Callback from user %s (@%s): %s in chat %s",
            user_id,
            username,
            data,
            chat_id,
        )

        if data == "join_game":
            await self._handle_join_game(
                chat_id, user_id, username, callback_query["id"]
            )
        elif data == "continue_guessing":
            await self._handle_continue_guessing(
                chat_id, user_id, username, callback_query["id"]
            )
        elif data == "next_question":
            await self._handle_next_question(
                chat_id, user_id, username, callback_query["id"]
            )
        elif data == "leaderboard":
            await self._handle_leaderboard(chat_id, callback_query["id"])
        elif data == "status":
            await self._handle_status(chat_id, callback_query["id"])
        elif data == "start_now":
            await self._handle_start_now(
                chat_id, user_id, username, callback_query["id"]
            )

    async def _handle_message(self, message: dict[str, Any]):
        try:
            chat_id = message["chat"]["id"]
            text = message.get("text", "").strip()
            user_id = message["from"]["id"]
            username = message["from"].get("username", "Unknown")

            logger.info(
                "Message from user %s (@%s): '%s' in chat %s",
                user_id,
                username,
                text,
                chat_id,
            )

            if not text:
                return

            text_lower = text.lower()

            if text_lower in ["/start", "начать игру", "старт"]:
                await self._handle_new_game(chat_id, user_id, username)
            elif text_lower in ["/stop", "стоп", "остановить игру"]:
                await self._handle_stop_game(chat_id, user_id, username)
            elif text_lower == "топ игроков":
                await self._handle_leaderboard_message(chat_id)
            elif text_lower == "статус":
                await self._handle_status_message(chat_id)
            else:
                has_active_game = await self._check_active_game(chat_id)
                if has_active_game:
                    await self._handle_game_answer(
                        chat_id, user_id, text, username
                    )

        except Exception:
            logger.exception("Error handling message")

    async def _send_inline_keyboard(
        self, chat_id: int, text: str, buttons: list[dict]
    ):
        try:
            keyboard = {"inline_keyboard": [list(row) for row in buttons]}

            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard
            )
            logger.info("Sent inline keyboard to chat %s", chat_id)
        except Exception:
            logger.error("Error sending inline keyboard")

    async def _handle_new_game(self, chat_id: int, user_id: int, username: str):
        logger.info("Creating new game by user %s in chat %s", user_id, chat_id)
        session = await self.app.store.game_accessor.create_session(
            chat_id, user_id, username
        )

        if session:
            buttons = [
                [
                    {
                        "text": "🎮 Добавиться в игру",
                        "callback_data": "join_game",
                    }
                ],
                [{"text": "🚀 Старт сейчас", "callback_data": "start_now"}],
                [{"text": "📊 Статус игры", "callback_data": "status"}],
                [{"text": "🏆 Топ игроков", "callback_data": "leaderboard"}],
            ]

            response = (
                f"🎮 *Игра '100 к 1' создана!*\n\n"
                f"👑 Создатель: @{username}\n"
                f"👥 Максимум игроков: 8\n"
                f"❓ Вопросов в игре: 5\n\n"
                f"⚡ *Присоединяйтесь к игре!*\n"
                f"Игра начнется автоматически через 60 секунд "
                f"или при 8 игроках\n"
                f"Создатель может запустить игру досрочно "
                f"кнопкой 'Старт сейчас'"
            )

            await self._send_inline_keyboard(chat_id, response, buttons)
            logger.info("Game session created successfully in chat %s", chat_id)
        else:
            response = (
                "❌ В этом чате уже есть активная игра! "
                "Дождитесь ее окончания."
            )
            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=response
            )
            logger.warning(
                "Game creation failed - active game exists in chat %s", chat_id
            )

    async def _handle_start_now(
        self, chat_id: int, user_id: int, username: str, callback_query_id: str
    ):
        try:
            logger.info(
                "User %s starting game now in chat %s", user_id, chat_id
            )
            (
                success,
                status,
            ) = await self.app.store.game_accessor.admin_start_game(
                chat_id, user_id
            )

            await self.app.store.telegram_api.answer_callback_query(
                callback_query_id,
                "✅ Игра запущена!"
                if success
                else "❌ Не удалось запустить игру",
            )

            response_messages = {
                "started": (
                    f"🚀 @{username} запустил игру досрочно!\n\n"
                    f"🏁 Игра начинается!"
                ),
                "no_session": "❌ Нет активной игры в ожидании.",
                "player_not_found": "❌ Игрок не найден.",
                "not_admin": (
                    "❌ Только создатель игры может запустить ее досрочно."
                ),
                "not_enough_players": (
                    "❌ Недостаточно игроков для старта (минимум 2)."
                ),
                "start_failed": "❌ Не удалось запустить игру.",
            }

            response = response_messages.get(
                status, "❌ Не удалось запустить игру."
            )

            if status != "started":
                await self.app.store.telegram_api.send_message(
                    chat_id=chat_id, text=response
                )

            logger.info("Start now result: %s by user %s", status, user_id)

        except Exception:
            logger.exception("Error starting game now")

    async def _handle_join_game(
        self, chat_id: int, user_id: int, username: str, callback_query_id: str
    ):
        try:
            logger.info("User %s joining game in chat %s", user_id, chat_id)
            (
                success,
                status,
            ) = await self.app.store.game_accessor.add_player_to_session(
                chat_id, user_id, username
            )

            if success:
                response_text = "✅ Вы присоединились к игре!"
            else:
                response_text = "❌ Не удалось присоединиться"

            await self.app.store.telegram_api.answer_callback_query(
                callback_query_id, response_text
            )

            response_messages = {
                "auto_started": (
                    f"🎉 @{username} присоединился к игре!\n\n"
                    f"🏁 Достигнуто 8 игроков! Игра начинается!"
                ),
                "started": (
                    f"🎉 @{username} присоединился к игре!\n\n"
                    f"🏁 Игра начинается!"
                ),
                "joined": await self._get_players_count_message(
                    chat_id, username
                ),
                "no_session": (
                    "❌ Нет активной игры в этом чате. "
                    "Начните игру командой 'старт'"
                ),
                "already_joined": f"ℹ️ @{username}, вы уже в игре!",
            }

            response = response_messages.get(
                status, "❌ Не удалось присоединиться к игре."
            )

            if status != "already_joined":
                await self.app.store.telegram_api.send_message(
                    chat_id=chat_id, text=response
                )

            logger.info("User %s join status: %s", user_id, status)

        except Exception:
            logger.exception("Error joining game")
            await self.app.store.telegram_api.answer_callback_query(
                callback_query_id, "❌ Ошибка при присоединении"
            )
            await self._send_error_message(
                chat_id, "Произошла ошибка при присоединении к игре"
            )

    async def _get_players_count_message(
        self, chat_id: int, username: str
    ) -> str:
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == "waiting_players",
                )
            )
            game_session_row = game_session_result.first()

            if game_session_row:
                game_session = game_session_row[0]
                players_count_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.session_id == game_session.id
                    )
                )
                players_count = len(players_count_result.scalars().all())
                return (
                    f"🎉 @{username} присоединился к игре! "
                    f"👥 Игроков: {players_count}/8"
                )
            return f"🎉 @{username} не присоединился к игре! 👥 Игроков: 0/8"

    async def _handle_continue_guessing(
        self, chat_id: int, user_id: int, username: str, callback_query_id: str
    ):
        logger.info("User %s continuing game in chat %s", user_id, chat_id)
        success = await self.app.store.game_accessor.continue_guessing(
            chat_id, user_id
        )

        await self.app.store.telegram_api.answer_callback_query(
            callback_query_id,
            "✅ Продолжаем угадывать!"
            if success
            else "❌ Не удалось продолжить",
        )

        if success:
            logger.info(
                "Game continued by user %s in chat %s", user_id, chat_id
            )
        else:
            logger.warning(
                "Continue game failed for user %s in chat %s", user_id, chat_id
            )

    async def _handle_next_question(
        self, chat_id: int, user_id: int, username: str, callback_query_id: str
    ):
        logger.info(
            "User %s moving to next question in chat %s", user_id, chat_id
        )
        success = await self.app.store.game_accessor.next_question(
            chat_id, user_id
        )

        await self.app.store.telegram_api.answer_callback_query(
            callback_query_id,
            "✅ Переходим к следующему вопросу!"
            if success
            else "❌ Не удалось перейти",
        )

        if success:
            logger.info(
                "Moved to next question by user %s in chat %s", user_id, chat_id
            )
        else:
            logger.warning(
                "Next question failed for user %s in chat %s", user_id, chat_id
            )

    async def _handle_leaderboard(self, chat_id: int, callback_query_id: str):
        logger.info("Showing leaderboard in chat %s", chat_id)
        await self.app.store.telegram_api.answer_callback_query(
            callback_query_id, "📊 Загружаем топ игроков..."
        )
        await self._handle_leaderboard_message(chat_id)

    async def _handle_leaderboard_message(self, chat_id: int):
        try:
            leaderboard = (
                await self.app.store.game_accessor.get_global_leaderboard()
            )
            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=leaderboard
            )
            logger.info("Leaderboard sent to chat %s", chat_id)
        except Exception:
            await self._send_error_message(
                chat_id, "❌ Ошибка при загрузке топа игроков"
            )

    async def _handle_status(self, chat_id: int, callback_query_id: str):
        logger.info("Showing status in chat %s", chat_id)
        await self.app.store.telegram_api.answer_callback_query(
            callback_query_id, "🔄 Загружаем статус..."
        )
        await self._handle_status_message(chat_id)

    async def _handle_status_message(self, chat_id: int):
        try:
            status = await self.app.store.game_accessor.get_game_status(chat_id)
            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=status
            )
            logger.info("Status sent to chat %s", chat_id)
        except Exception:
            logger.exception("Error sending status")
            await self._send_error_message(
                chat_id, "Ошибка при получении статуса"
            )

    async def _check_active_game(self, chat_id: int) -> bool:
        try:
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(
                            [
                                "question_start",
                                "accepting_answers",
                                "showing_results",
                                "round_transition",
                            ]
                        ),
                    )
                )
                active = game_session_result.first() is not None
                logger.debug(
                    "Active game check in chat %s: %s", chat_id, active
                )
                return active
        except Exception:
            logger.error("Error checking active game")
            return False

    async def _handle_stop_game(
        self, chat_id: int, user_id: int, username: str
    ):
        try:
            logger.info("User %s stopping game in chat %s", user_id, chat_id)
            status = await self.app.store.game_accessor.stop_game(
                chat_id, user_id
            )

            response_messages = {
                "stopped": (
                    f"🛑 @{username} остановил игру!\n\n🏁 Игра завершена."
                ),
                "no_active_game": "❌ Нет активной игры для остановки.",
                "player_not_found": "❌ Игрок не найден.",
                "not_admin": (
                    "❌ Только создатель игры может остановить игру."
                ),
            }

            response = response_messages.get(status)
            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=response
            )

            logger.info("Game stop result: %s by user %s", status, user_id)

        except Exception:
            logger.exception("Error stopping game")
            await self._send_error_message(
                chat_id, "Произошла ошибка при остановке игры"
            )

    async def _handle_game_answer(
        self, chat_id: int, user_id: int, answer_text: str, username: str
    ):
        try:
            logger.info(
                "User %s submitting answer in chat %s: '%s'",
                user_id,
                chat_id,
                answer_text,
            )
            result = await self.app.store.game_accessor.submit_answer(
                chat_id, user_id, answer_text
            )
            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=result["message"]
            )
        except Exception:
            logger.exception("Error submitting answer")
            await self._send_error_message(
                chat_id, "Произошла ошибка при отправке ответа"
            )

    async def _send_error_message(self, chat_id: int, message: str):
        await self.app.store.telegram_api.send_message(
            chat_id=chat_id, text=message
        )
        logger.error("Sent error message to chat %s: %s", chat_id, message)
