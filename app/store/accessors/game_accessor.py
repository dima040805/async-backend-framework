import asyncio
import datetime
import logging
import typing

from sqlalchemy import desc, func, select

from app.models.database import (
    AnswerVariant,
    GameSession,
    Player,
    PlayerAnswer,
    Question,
    SessionPlayer,
)
from app.store.database.base_accessor import BaseAccessor

# ruff: noqa: PLR0915, PLR0914, PLR1702, PLR0911, RUF006
if typing.TYPE_CHECKING:
    from app.web.app import Application

logger = logging.getLogger(__name__)


class GameAccessor(BaseAccessor):
    def __init__(self, app: "Application"):
        super().__init__(app)

    def _normalize_answer(self, text: str) -> str:
        """Нормализация ответа для сравнения"""
        if not text:
            return ""
        return " ".join(text.lower().strip().split())

    async def _clear_old_timers(self, chat_id: int):
        """Очищает старые идентификаторы таймеров при смене состояния"""
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(GameSession.chat_id == chat_id)
            )
            game_session_row = game_session_result.first()

            if game_session_row:
                game_session = game_session_row[0]
                game_session.current_timer_id = None
                await session.commit()
                logger.info("Cleared timer ID for chat %s", chat_id)

    async def _round_timer(self, chat_id: int, duration: int):
        """Таймер раунда с защитой от старых срабатываний"""
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == "accepting_answers",
                )
            )
            game_session_row = game_session_result.first()

            if not game_session_row:
                logger.info(
                    "Timer CANCELLED - game not in accepting_answers state "
                    "for chat %s",
                    chat_id,
                )
                return

            current_session = game_session_row[0]
            timer_id = (
                f"Q{current_session.current_question_number}"
                f"R{current_session.current_question_round}"
            )

            current_session.current_timer_id = timer_id
            await session.commit()

        logger.info(
            "Round timer STARTED: %s, %ss for chat %s",
            timer_id,
            duration,
            chat_id,
        )

        await asyncio.sleep(duration)

        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == "accepting_answers",
                    GameSession.current_timer_id == timer_id,
                )
            )
            game_session_row = game_session_result.first()

            if game_session_row:
                logger.info("Timer FINISHED: %s in chat %s", timer_id, chat_id)
                await self._finish_round(chat_id)
            else:
                logger.info(
                    "Timer EXPIRED (obsolete): %s for chat %s - game moved on",
                    timer_id,
                    chat_id,
                )

    async def create_session(
        self,
        chat_id: int,
        creator_telegram_id: int,
        username: str | None = None,
    ) -> GameSession | None:
        try:
            logger.info(
                "Creating session for chat %s by user %s",
                chat_id,
                creator_telegram_id,
            )

            async with self.app.store.database.session() as session:
                existing_session = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(
                            [
                                "waiting_players",
                                "question_start",
                                "accepting_answers",
                                "showing_results",
                                "round_transition",
                            ]
                        ),
                    )
                )
                if existing_session.first():
                    logger.warning("Active session exists in chat %s", chat_id)
                    return None

                player = await session.execute(
                    select(Player).where(
                        Player.telegram_id == creator_telegram_id
                    )
                )
                player = player.scalar_one_or_none()

                if not player:
                    player = Player(
                        telegram_id=creator_telegram_id,
                        username=username,
                        games_played=0,
                        wins=0,
                        total_points=0,
                        rating=1000,
                    )
                    session.add(player)
                    await session.commit()
                    await session.refresh(player)
                    logger.info("Created new player: %s", player.id)

                game_session = GameSession(
                    chat_id=chat_id,
                    state="waiting_players",
                    total_questions=5,
                    current_question_number=0,
                    current_question_round=1,
                    max_rounds_per_question=3,
                    current_timer_id=None,
                )
                session.add(game_session)
                await session.commit()
                await session.refresh(game_session)

                session_player = SessionPlayer(
                    player_id=player.id,
                    session_id=game_session.id,
                    is_admin=True,
                    final_score=0,
                )
                session.add(session_player)
                await session.commit()

                logger.info(
                    "Game session %s created for chat %s",
                    game_session.id,
                    chat_id,
                )

                _ = asyncio.create_task(
                    self._waiting_players_timer(game_session.id, chat_id, 60)
                )

                return game_session

        except Exception:
            logger.exception("Error creating session")
            return None

    async def _waiting_players_timer(
        self, session_id: int, chat_id: int, duration: int
    ):
        """Таймер ожидания игроков"""
        logger.info(
            "Waiting players timer started: %ss for session %s",
            duration,
            session_id,
        )
        await asyncio.sleep(duration)

        async with self.app.store.database.session() as session:
            game_session = await session.get(GameSession, session_id)

            if game_session and game_session.state == "waiting_players":
                players_count_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.session_id == session_id
                    )
                )
                players_count = len(players_count_result.scalars().all())

                if players_count >= 2:
                    success = await self._start_first_question(chat_id)
                    if success:
                        await self.app.store.telegram_api.send_message(
                            chat_id=chat_id,
                            text="⏰ Время вышло! Игра начинается!",
                        )
                        logger.info(
                            "Auto-started game in chat %s timer", chat_id
                        )
                    else:
                        await self.app.store.telegram_api.send_message(
                            chat_id=chat_id,
                            text="❌ Не удалось начать игру.",
                        )
                else:
                    game_session.state = "finished"
                    await session.commit()
                    await self.app.store.telegram_api.send_message(
                        chat_id=chat_id,
                        text=(
                            "⏰ Время вышло! Недостаточно игроков. "
                            "Игра отменена."
                        ),
                    )
                    logger.info(
                        "Game cancelled in chat %s - < players", chat_id
                    )

    async def _start_first_question(self, chat_id: int) -> bool:
        try:
            logger.info("Starting first question in chat %s", chat_id)

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == "waiting_players",
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No waiting session for chat %s", chat_id)
                    return False

                game_session = game_session_row[0]

                players_count_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.session_id == game_session.id
                    )
                )
                players_count = len(players_count_result.scalars().all())

                if players_count < 2:
                    logger.warning(
                        "Not enough players (%s) to start game in chat %s",
                        players_count,
                        chat_id,
                    )
                    return False

                question = await self._get_random_question(session, game_session.id)
                if not question:
                    logger.error("No active questions for chat %s", chat_id)
                    return False

                game_session.state = "question_start"
                game_session.current_question_number = 1
                game_session.current_question_round = 1
                game_session.current_question_id = question.id
                await session.commit()

                await self._send_question_to_chat(chat_id, question, 1, 1)

                game_session.state = "accepting_answers"
                await session.commit()

                _ = asyncio.create_task(self._round_timer(chat_id, 45))

                logger.info("First question started in chat %s", chat_id)
                return True

        except Exception:
            logger.exception("Error starting first question")
            return False

    async def _send_question_to_chat(
        self,
        chat_id: int,
        question: Question,
        question_number: int,
        round_number: int,
    ):
        """Отправка вопроса с кнопками"""
        message = (
            f"🎯 *ВОПРОС №{question_number} | РАУНД {round_number}*\n\n"
            f"❓ {question.text}\n\n"
            f"📝 *Правила:*\n"
            f"• Присылайте свои ответы в чат\n"
            f"• Каждый игрок может дать только 1 ответ за раунд\n"
            f"• Ответы принимаются 45 секунд\n"
            f"• Угадывайте самые популярные ответы!\n\n"
            f"⏰ *Время пошло!*"
        )

        await self.app.store.telegram_api.send_message(
            chat_id=chat_id, text=message
        )
        logger.info(
            "Question %s round %s sent to chat %s",
            question_number,
            round_number,
            chat_id,
        )

    async def _finish_round(self, chat_id: int):
        try:
            logger.info("Finishing round in chat %s", chat_id)

            await self._clear_old_timers(chat_id)

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == 'accepting_answers'                
                        ))
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No active game for chat %s", chat_id)
                    return

                game_session = game_session_row[0]

                answers_result = await session.execute(
                    select(PlayerAnswer).where(
                        PlayerAnswer.session_id == game_session.id,
                        PlayerAnswer.round
                        == (game_session.current_question_round),
                    )
                )
                answers = answers_result.scalars().all()

                variants_result = await session.execute(
                    select(AnswerVariant)
                    .where(
                        AnswerVariant.question_id
                        == (game_session.current_question_id)
                    )
                    .order_by(AnswerVariant.position)
                )
                all_variants = variants_result.scalars().all()

                logger.info(
                    "Processing %s answers against %s variants",
                    len(answers),
                    len(all_variants),
                )

                already_guessed_variants_result = await session.execute(
                    select(PlayerAnswer).where(
                        PlayerAnswer.session_id == game_session.id,
                        PlayerAnswer.question_id
                        == (game_session.current_question_id),
                        PlayerAnswer.round
                        < (game_session.current_question_round),
                        PlayerAnswer.points_earned > 0,
                    )
                )
                already_guessed_answers = (
                    already_guessed_variants_result.scalars().all()
                )

                already_guessed_texts = {
                    self._normalize_answer(guessed_answer.answer_text)
                    for guessed_answer in already_guessed_answers
                }

                logger.info(
                    "Already guessed variants: %s",
                    already_guessed_texts,
                )

                round_scored_variants = []
                newly_revealed_variant_ids = []

                for variant in all_variants:
                    variant_answers = []
                    normalized_variant = self._normalize_answer(variant.text)

                    if normalized_variant in already_guessed_texts:
                        logger.info(
                            "Skipping variant '%s' - already guessed",
                            variant.text,
                        )
                        continue

                    for answer in answers:
                        if (
                            self._normalize_answer(answer.answer_text)
                            == normalized_variant
                        ):
                            logger.info(
                                "Match in round %s: '%s' == '%s'",
                                game_session.current_question_round,
                                answer.answer_text,
                                variant.text,
                            )

                            player_result = await session.execute(
                                select(Player).where(
                                    Player.id == answer.player_id
                                )
                            )
                            player = player_result.scalar_one()

                            variant_answers.append(
                                {
                                    "player_id": player.id,
                                    "telegram_id": player.telegram_id,
                                    "username": player.username,
                                    "answer_id": answer.id,
                                }
                            )

                    if variant_answers:
                        points_per_player = variant.points
                        logger.info(
                            "Awarding %s points to %s players",
                            points_per_player,
                            len(variant_answers),
                        )

                        for answer_info in variant_answers:
                            answer_update = await session.execute(
                                select(PlayerAnswer).where(
                                    PlayerAnswer.id
                                    == (answer_info["answer_id"])
                                )
                            )
                            player_answer = answer_update.scalar_one()
                            player_answer.points_earned = points_per_player

                            session_player_update = await session.execute(
                                select(SessionPlayer).where(
                                    SessionPlayer.player_id
                                    == (answer_info["player_id"]),
                                    SessionPlayer.session_id
                                    == (game_session.id),
                                )
                            )
                            session_player = session_player_update.scalar_one()
                            session_player.final_score += points_per_player

                        round_scored_variants.append(
                            {
                                "variant": variant,
                                "answers": variant_answers,
                                "points_per_player": points_per_player,
                            }
                        )
                        newly_revealed_variant_ids.append(variant.id)

                game_session.state = "showing_results"
                await session.commit()

                await self._show_all_round_results(chat_id, game_session)

                all_variants_revealed = len(newly_revealed_variant_ids) == len(
                    all_variants
                )
                max_rounds_reached = (
                    game_session.current_question_round
                    >= game_session.max_rounds_per_question
                )

                if all_variants_revealed or max_rounds_reached:
                    await self._finish_question(chat_id)
                else:
                    game_session.state = "round_transition"
                    await session.commit()
                    await self._ask_admin_decision(chat_id, game_session)

        except Exception:
            logger.exception("Error finishing round")

    async def _show_all_round_results(
        self, chat_id: int, game_session: GameSession
    ):
        async with self.app.store.database.session() as session:
            variants_result = await session.execute(
                select(AnswerVariant)
                .where(
                    AnswerVariant.question_id
                    == (game_session.current_question_id)
                )
                .order_by(AnswerVariant.position)
            )
            all_variants = variants_result.scalars().all()

            all_answers_result = await session.execute(
                select(PlayerAnswer).where(
                    PlayerAnswer.session_id == game_session.id,
                    PlayerAnswer.question_id
                    == (game_session.current_question_id),
                )
            )
            all_answers = all_answers_result.scalars().all()

            message = (
                f"🎉 *Результаты вопроса "
                f"{game_session.current_question_number}:*\n\n"
            )

            revealed_count = 0

            for variant in all_variants:
                players_list = []

                for answer in all_answers:
                    if self._normalize_answer(
                        answer.answer_text
                    ) == self._normalize_answer(variant.text):
                        player_result = await session.execute(
                            select(Player).where(Player.id == answer.player_id)
                        )
                        player = player_result.scalar_one()
                        username = (
                            player.username or f"игрок {player.telegram_id}"
                        )

                        if username not in players_list:
                            players_list.append(f"@{username}")

                if players_list:
                    revealed_count += 1
                    players_str = ", ".join(players_list)
                    message += (
                        f"{variant.position}. *{variant.text}* - "
                        f"{variant.points} очков ({players_str})\n"
                    )
                else:
                    message += f"{variant.position}. - {variant.points} очков\n"

            message += f"\n📊 Открыто: {revealed_count}/{len(all_variants)}"
            message += f"\n🎯 Раунд: {game_session.current_question_round}"

            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=message
            )
            logger.info("All round results sent to chat %s", chat_id)

    async def _ask_admin_decision(
        self, chat_id: int, game_session: GameSession
    ):
        """Запрашивает решение у создателя игры"""
        message = (
            f"🎯 Вопрос {game_session.current_question_number} | "
            f"Раунд {game_session.current_question_round} завершен!\n\n"
            f"*Что делаем дальше?*\n\n"
            f"Создатель игры, выберите действие:"
        )

        buttons = [
            [
                {
                    "text": "🔄 Продолжить угадывать",
                    "callback_data": "continue_guessing",
                },
                {
                    "text": "➡️ Следующий вопрос",
                    "callback_data": "next_question",
                },
            ]
        ]

        await self.app.store.telegram_api.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup={"inline_keyboard": buttons},
        )
        logger.info("Admin decision requested in chat %s", chat_id)

    async def continue_guessing(
        self, chat_id: int, admin_telegram_id: int
    ) -> bool:
        """Продолжить угадывать текущий вопрос"""
        try:
            logger.info(
                "Continuing game in chat %s by user %s",
                chat_id,
                admin_telegram_id,
            )

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == "round_transition",
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No game in transition for chat %s", chat_id)
                    return False

                game_session = game_session_row[0]

                is_admin = await self._check_admin_rights(
                    session, game_session.id, admin_telegram_id
                )
                if not is_admin:
                    logger.warning(
                        "User %s not admin in chat %s",
                        admin_telegram_id,
                        chat_id,
                    )
                    return False

                await self._clear_old_timers(chat_id)

                game_session.current_question_round += 1
                game_session.state = "accepting_answers"
                await session.commit()

                question_result = await session.execute(
                    select(Question).where(
                        Question.id == game_session.current_question_id
                    )
                )
                question = question_result.scalar_one()

                await self._send_question_to_chat(
                    chat_id,
                    question,
                    game_session.current_question_number,
                    game_session.current_question_round,
                )

                _ = asyncio.create_task(self._round_timer(chat_id, 45))

                logger.info(
                    "Game continued in chat %s, round %s",
                    chat_id,
                    game_session.current_question_round,
                )
                return True

        except Exception:
            logger.exception("Error continuing game")
            return False

    async def next_question(self, chat_id: int, admin_telegram_id: int) -> bool:
        """Перейти к следующему вопросу"""
        try:
            logger.info(
                "Moving to next question in chat %s by user %s",
                chat_id,
                admin_telegram_id,
            )

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == "round_transition",
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No game in transition for chat %s", chat_id)
                    return False

                game_session = game_session_row[0]

                is_admin = await self._check_admin_rights(
                    session, game_session.id, admin_telegram_id
                )
                if not is_admin:
                    logger.warning(
                        "User %s not admin in chat %s",
                        admin_telegram_id,
                        chat_id,
                    )
                    return False

                await self._show_final_question_results(chat_id, game_session)
                await self._clear_old_timers(chat_id)

                game_session.current_question_number += 1
                game_session.current_question_round = 1

                if (
                    game_session.current_question_number
                    > game_session.total_questions
                ):
                    logger.info("Game finished in chat %s", chat_id)
                    await self._finish_game(chat_id, game_session)
                    return True

                question = await self._get_random_question(session, game_session.id)
                if not question:
                    logger.error("No active questions for chat %s", chat_id)
                    return False

                game_session.current_question_id = question.id
                game_session.state = "accepting_answers"
                await session.commit()

                await self._send_question_to_chat(
                    chat_id,
                    question,
                    game_session.current_question_number,
                    game_session.current_question_round,
                )

                _ = asyncio.create_task(self._round_timer(chat_id, 45))

                logger.info(
                    "Moved to question %s in chat %s",
                    game_session.current_question_number,
                    chat_id,
                )
                return True

        except Exception:
            logger.exception("Error moving to next question")
            return False

    async def _finish_game(self, chat_id: int, game_session: GameSession):
        """Завершает игру и показывает результаты"""
        try:
            logger.info("Finishing game in chat %s", chat_id)

            await self._clear_old_timers(chat_id)
            await self._update_player_stats(game_session.id)
            await self._show_final_results(chat_id, game_session.id)

            async with self.app.store.database.session() as session:
                session_game = await session.get(GameSession, game_session.id)
                session_game.state = "finished"
                await session.commit()

            logger.info("Game finished in chat %s", chat_id)

        except Exception:
            logger.exception("Error finishing game")

    async def _finish_question(self, chat_id: int):
        try:
            logger.info("Finishing question in chat %s", chat_id)

            await self._clear_old_timers(chat_id)

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(['showing_results', 'round_transition'])                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No active game for chat %s", chat_id)
                    return

                game_session = game_session_row[0]

                await self._show_final_question_results(chat_id, game_session)

                game_session.current_question_number += 1
                game_session.current_question_round = 1

                if (
                    game_session.current_question_number
                    > game_session.total_questions
                ):
                    logger.info("Game finished in chat %s", chat_id)
                    await self._finish_game(chat_id, game_session)
                    return

                question = await self._get_random_question(session, game_session.id)
                if not question:
                    game_session.state = "finished"
                    await session.commit()
                    await self.app.store.telegram_api.send_message(
                        chat_id=chat_id,
                        text=("❌ Не удалось найти вопрос. " "Игра завершена."),
                    )
                    logger.error("No active questions for chat %s", chat_id)
                    return

                game_session.current_question_id = question.id
                game_session.state = "accepting_answers"
                await session.commit()

                await self._send_question_to_chat(
                    chat_id,
                    question,
                    game_session.current_question_number,
                    game_session.current_question_round,
                )

                _ = asyncio.create_task(self._round_timer(chat_id, 45))

                logger.info(
                    "Moved to question %s in chat %s",
                    game_session.current_question_number,
                    chat_id,
                )

        except Exception:
            logger.exception("Error finishing question")

    async def _show_final_question_results(
        self, chat_id: int, game_session: GameSession
    ):
        try:
            logger.info(
                "Showing final results for question %s in chat %s",
                game_session.current_question_number,
                chat_id,
            )

            async with self.app.store.database.session() as session:
                question_result = await session.execute(
                    select(Question).where(
                        Question.id == game_session.current_question_id
                    )
                )
                question = question_result.scalar_one()

                variants_result = await session.execute(
                    select(AnswerVariant)
                    .where(
                        AnswerVariant.question_id
                        == (game_session.current_question_id)
                    )
                    .order_by(AnswerVariant.position)
                )
                all_variants = variants_result.scalars().all()

                answers_result = await session.execute(
                    select(PlayerAnswer).where(
                        PlayerAnswer.session_id == game_session.id,
                        PlayerAnswer.question_id
                        == (game_session.current_question_id),
                    )
                )
                all_answers = answers_result.scalars().all()

                message = (
                    f"🏁 *ВОПРОС {game_session.current_question_number} "
                    f"ЗАВЕРШЕН!*\n\n"
                )
                message += f"❓ *Вопрос:* {question.text}\n\n"
                message += "📋 *ВСЕ ВАРИАНТЫ ОТВЕТОВ:*\n\n"

                total_points_earned = 0
                revealed_variants = 0

                for variant in all_variants:
                    players_who_answered = []
                    variant_points_earned = 0

                    for answer in all_answers:
                        if self._normalize_answer(
                            answer.answer_text
                        ) == self._normalize_answer(variant.text):
                            player_result = await session.execute(
                                select(Player).where(
                                    Player.id == answer.player_id
                                )
                            )
                            player = player_result.scalar_one()
                            username = (
                                player.username or f"игрок {player.telegram_id}"
                            )

                            if f"@{username}" not in players_who_answered:
                                players_who_answered.append(f"@{username}")
                                variant_points_earned += answer.points_earned

                    if players_who_answered:
                        revealed_variants += 1
                        players_str = ", ".join(players_who_answered)
                        message += (
                            f"✅ {variant.position}. *{variant.text}* - "
                            f"{variant.points} очков\n"
                        )
                        message += f"   👤 Угадали: {players_str}\n"
                        message += (
                            f"   💰 Получено: {variant_points_earned} "
                            f"очков\n\n"
                        )
                        total_points_earned += variant_points_earned
                    else:
                        message += (
                            f"❌ {variant.position}. *{variant.text}* - "
                            f"{variant.points} очков\n"
                        )
                        message += "👤 Никто не угадал\n\n"

                message += "📊 *ИТОГИ ВОПРОСА:*\n"
                message += (
                    f"• Открыто: {revealed_variants}/{len(all_variants)}\n"
                )
                message += f"• Заработано: {total_points_earned} очков\n"
                message += (
                    f"• Раундов: {game_session.current_question_round}\n\n"
                )

                if (
                    game_session.current_question_number
                    < game_session.total_questions
                ):
                    message += (
                        f"➡️ *Переходим к вопросу "
                        f"{game_session.current_question_number + 1} "
                        f"из {game_session.total_questions}*"
                    )
                else:
                    message += "🎉 *Это был последний вопрос!*"

                await self.app.store.telegram_api.send_message(
                    chat_id=chat_id, text=message
                )
                logger.info("Final question results sent to chat %s", chat_id)

        except Exception:
            logger.exception("Error showing final question results")

    async def _update_player_stats(self, session_id: int):
        """Обновляет статистику игроков после игры"""
        async with self.app.store.database.session() as session:
            session_players_result = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.session_id == session_id
                )
            )
            session_players = session_players_result.scalars().all()

            if not session_players:
                logger.warning("No players for session %s", session_id)
                return

            player_ids = [sp.player_id for sp in session_players]

            players_result = await session.execute(
                select(Player).where(Player.id.in_(player_ids))
            )
            players = {
                player.id: player for player in players_result.scalars().all()
            }

            winner = max(session_players, key=lambda sp: sp.final_score)

            for session_player in session_players:
                player = players.get(session_player.player_id)
                if not player:
                    logger.warning(
                        "Player %s not found",
                        session_player.player_id,
                    )
                    continue

                player.games_played += 1
                player.total_points += session_player.final_score
                player.date_last_game = datetime.datetime.utcnow()

                if session_player.id == winner.id:
                    player.wins += 1
                    logger.info(
                        "Player %s won session %s",
                        player.id,
                        session_id,
                    )

                session.add(player)

            await session.commit()
            logger.info("Updated stats for %s players", len(session_players))

    async def _show_final_results(self, chat_id: int, session_id: int):
        """Показывает финальные результаты игры"""
        async with self.app.store.database.session() as session:
            session_players_result = await session.execute(
                select(SessionPlayer)
                .where(SessionPlayer.session_id == session_id)
                .order_by(desc(SessionPlayer.final_score))
            )
            session_players = session_players_result.scalars().all()

            if not session_players:
                logger.warning(
                    "No players for final results in session %s",
                    session_id,
                )
                return

            player_ids = [sp.player_id for sp in session_players]

            players_result = await session.execute(
                select(Player).where(Player.id.in_(player_ids))
            )
            players_dict = {
                player.id: player for player in players_result.scalars().all()
            }

            message = "🏆 *ФИНАЛЬНЫЕ РЕЗУЛЬТАТЫ ИГРЫ:*\n\n"

            for i, session_player in enumerate(session_players, 1):
                player = players_dict.get(session_player.player_id)
                if player:
                    username = player.username or f"игрок {player.telegram_id}"
                    message += (
                        f"{i}. @{username} - "
                        f"{session_player.final_score} очков\n"
                    )
                else:
                    message += (
                        f"{i}. Игрок {session_player.player_id} - "
                        f"{session_player.final_score} очков\n"
                    )

            if session_players:
                winner_session_player = session_players[0]
                winner_player = players_dict.get(
                    winner_session_player.player_id
                )
                if winner_player:
                    winner_username = (
                        winner_player.username
                        or f"игрок {winner_player.telegram_id}"
                    )
                    message += f"\n🎉 *ПОБЕДИТЕЛЬ: @{winner_username}* 🎉\n\n"
                else:
                    message += (
                        f"\n🎉 *ПОБЕДИТЕЛЬ: Игрок "
                        f"{winner_session_player.player_id}* 🎉\n\n"
                    )

            message += "Спасибо за игру! Чтобы начать новую, напишите 'старт'"

            await self.app.store.telegram_api.send_message(
                chat_id=chat_id, text=message
            )
            logger.info("Final results sent to chat %s", chat_id)

    async def _check_admin_rights(
        self, session, session_id: int, telegram_id: int
    ) -> bool:
        """Проверяет, является ли пользователь админом сессии"""
        player_result = await session.execute(
            select(Player).where(Player.telegram_id == telegram_id)
        )
        player = player_result.scalar_one_or_none()

        if not player:
            return False

        admin_check = await session.execute(
            select(SessionPlayer).where(
                SessionPlayer.player_id == player.id,
                SessionPlayer.session_id == session_id,
                SessionPlayer.is_admin,
            )
        )

        return admin_check.first() is not None

    async def _get_random_question(
        self, session, session_id: int = None, excluded_question_ids: list[int] | None = None
    ) -> Question | None:
        """Получает случайный активный вопрос, исключая уже использованные"""
        if excluded_question_ids is None:
            excluded_question_ids = []

        # Если передан session_id, получаем вопросы которые уже использовались в этой сессии
        if session_id:
            used_questions_result = await session.execute(
                select(PlayerAnswer.question_id)
                .where(PlayerAnswer.session_id == session_id)
                .distinct()
            )
            used_question_ids = [q[0] for q in used_questions_result.all()]
            excluded_question_ids.extend(used_question_ids)

        query = select(Question).where(Question.is_active)

        if excluded_question_ids:
            query = query.where(Question.id.notin_(excluded_question_ids))

        question_result = await session.execute(
            query.order_by(func.random()).limit(1)
        )
        question = question_result.scalar_one_or_none()

        if question:
            logger.info(
                "Selected question: %s - '%s' (excluded: %s)",
                question.id,
                question.text,
                excluded_question_ids,
            )
        else:
            logger.warning(
                "No available questions (excluded: %s)",
                excluded_question_ids,
            )

        return question

    async def add_player_to_session(
        self, chat_id: int, telegram_id: int, username: str | None = None
    ) -> tuple[bool, str]:
        try:
            logger.info(
                "Adding player %s to session in chat %s",
                telegram_id,
                chat_id,
            )

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == "waiting_players",
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No waiting session in chat %s", chat_id)
                    return False, "no_session"

                game_session = game_session_row[0]
                logger.info("Found session %s", game_session.id)

                player_result = await session.execute(
                    select(Player).where(Player.telegram_id == telegram_id)
                )
                player = player_result.scalar_one_or_none()

                if not player:
                    player = Player(
                        telegram_id=telegram_id,
                        username=username,
                        games_played=0,
                        wins=0,
                        total_points=0,
                        rating=1000,
                    )
                    session.add(player)
                    await session.commit()
                    await session.refresh(player)
                    logger.info("CREATED_NEW_PLAYER: player_id=%s", player.id)

                existing_player_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.player_id == player.id,
                        SessionPlayer.session_id == game_session.id,
                    )
                )
                if existing_player_result.first():
                    logger.info(
                        "Player %s already joined session %s",
                        telegram_id,
                        game_session.id,
                    )
                    return False, "already_joined"

                session_player = SessionPlayer(
                    player_id=player.id,
                    session_id=game_session.id,
                    is_admin=False,
                    final_score=0,
                )
                session.add(session_player)
                await session.commit()

                logger.info(
                    "Player %s added to session %s",
                    telegram_id,
                    game_session.id,
                )

                players_count_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.session_id == game_session.id
                    )
                )
                players_count = len(players_count_result.scalars().all())
                logger.info("CURRENT_PLAYERS_COUNT: %s/8", players_count)

                if players_count >= 8:
                    logger.info("Auto-starting game in chat %s", chat_id)
                    success = await self._start_first_question(chat_id)
                    if success:
                        return True, "auto_started"
                    return True, "joined"

                return True, "joined"

        except Exception:
            logger.exception("Error adding player to session")
            return False, "error"

    async def admin_start_game(
        self, chat_id: int, admin_telegram_id: int
    ) -> tuple[bool, str]:
        """Запускает игру досрочно (админом)"""
        try:
            logger.info(
                "Admin starting game in chat %s by user %s",
                chat_id,
                admin_telegram_id,
            )

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == "waiting_players",
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No waiting session for chat %s", chat_id)
                    return False, "no_session"

                game_session = game_session_row[0]

                player_result = await session.execute(
                    select(Player).where(
                        Player.telegram_id == admin_telegram_id
                    )
                )
                player = player_result.scalar_one_or_none()

                if not player:
                    logger.warning("Player %s not found", admin_telegram_id)
                    return False, "player_not_found"

                admin_check = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.player_id == player.id,
                        SessionPlayer.session_id == game_session.id,
                        SessionPlayer.is_admin,
                    )
                )

                if not admin_check.first():
                    logger.warning(
                        "User %s not admin in session %s",
                        admin_telegram_id,
                        game_session.id,
                    )
                    return False, "not_admin"

                players_count_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.session_id == game_session.id
                    )
                )
                players_count = len(players_count_result.scalars().all())

                if players_count < 2:
                    logger.warning(
                        "Not enough players (%s) in chat %s",
                        players_count,
                        chat_id,
                    )
                    return False, "not_enough_players"

                success = await self._start_first_question(chat_id)
                if success:
                    logger.info("Game started by admin in chat %s", chat_id)
                    return True, "started"
                logger.error("Failed to start game in chat %s", chat_id)
                return False, "start_failed"

        except Exception:
            logger.exception("Error in admin start")
            return False, "error"

    async def submit_answer(
        self, chat_id: int, telegram_id: int, answer_text: str
    ) -> dict[str, typing.Any]:
        """Отправляет ответ игрока (БЕЗ ПРОВЕРКИ СРАЗУ)"""
        try:
            logger.info(
                "Submitting answer from user %s in chat %s: '%s'",
                telegram_id,
                chat_id,
                answer_text,
            )

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == "accepting_answers",
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No active game session in chat %s", chat_id)
                    return {
                        "success": False,
                        "message": "Нет активной сессии",
                    }

                game_session = game_session_row[0]

                player_result = await session.execute(
                    select(Player).where(Player.telegram_id == telegram_id)
                )
                player = player_result.scalar_one_or_none()

                if not player:
                    logger.warning("Player %s not found", telegram_id)
                    return {
                        "success": False,
                        "message": "Игрок не найден",
                    }

                session_player_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.player_id == player.id,
                        SessionPlayer.session_id == game_session.id,
                    )
                )
                if not session_player_result.first():
                    logger.warning(
                        "Player %s not in session %s",
                        telegram_id,
                        game_session.id,
                    )
                    return {
                        "success": False,
                        "message": "Вы не в игре",
                    }

                existing_answer = await session.execute(
                    select(PlayerAnswer).where(
                        PlayerAnswer.player_id == player.id,
                        PlayerAnswer.session_id == game_session.id,
                        PlayerAnswer.question_id
                        == (game_session.current_question_id),
                        PlayerAnswer.round
                        == (game_session.current_question_round),
                    )
                )
                if existing_answer.first():
                    logger.info(
                        "Player %s already answered in this round",
                        telegram_id,
                    )
                    return {
                        "success": False,
                        "message": "В этом раунде вы уже отвечали",
                    }

                player_answer = PlayerAnswer(
                    player_id=player.id,
                    session_id=game_session.id,
                    question_id=game_session.current_question_id,
                    round=game_session.current_question_round,
                    answer_text=answer_text,
                    normalized_text=self._normalize_answer(answer_text),
                    points_earned=0,
                )
                session.add(player_answer)
                await session.commit()

                logger.info(
                    "Answer submitted by %s (not checked yet)",
                    telegram_id,
                )

                all_answered = await self._check_all_players_answered(chat_id)
                if all_answered:
                    logger.info(
                        "All players answered in chat %s, finishing round",
                        chat_id,
                    )
                    _ = asyncio.create_task(self._finish_round(chat_id))

                return {
                    "success": True,
                    "message": ("✅ Ответ принят! Ждем остальных игроков..."),
                }

        except Exception:
            logger.exception("Error submitting answer")
            return {
                "success": False,
                "message": "Error submitting answer",
            }

    async def _check_all_players_answered(self, chat_id: int) -> bool:
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == "accepting_answers",
                )
            )
            game_session_row = game_session_result.first()

            if not game_session_row:
                return False

            game_session = game_session_row[0]

            players_result = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.session_id == game_session.id
                )
            )
            players = players_result.scalars().all()

            answers_result = await session.execute(
                select(PlayerAnswer).where(
                    PlayerAnswer.session_id == game_session.id,
                    PlayerAnswer.question_id
                    == (game_session.current_question_id),
                    PlayerAnswer.round == (game_session.current_question_round),
                )
            )
            answered_players = answers_result.scalars().all()

            answered_player_ids = {
                answer.player_id for answer in answered_players
            }
            all_player_ids = {sp.player_id for sp in players}

            all_answered = answered_player_ids == all_player_ids

            logger.info(
                "All players check: %s total, %s answered = %s",
                len(all_player_ids),
                len(answered_player_ids),
                all_answered,
            )

            return all_answered

    async def stop_game(self, chat_id: int, user_id: int) -> tuple[bool, str]:
        """Останавливает игру и показывает результаты"""
        try:
            logger.info("Stopping game in chat %s by user %s", chat_id, user_id)

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession)
                    .where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(
                            [
                                "waiting_players",
                                "question_start",
                                "accepting_answers",
                                "showing_results",
                                "round_transition",
                            ]
                        ),
                    )
                    .order_by(GameSession.id.desc())
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    logger.warning("No active game to stop in chat %s", chat_id)
                    return False, "no_active_game"

                game_session = game_session_row[0]

                player_result = await session.execute(
                    select(Player).where(Player.telegram_id == user_id)
                )
                player = player_result.scalar_one_or_none()

                if not player:
                    logger.warning("Player %s not found", user_id)
                    return False, "player_not_found"

                admin_check = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.player_id == player.id,
                        SessionPlayer.session_id == game_session.id,
                        SessionPlayer.is_admin,
                    )
                )

                if not admin_check.first():
                    logger.warning(
                        "User %s not admin in session %s",
                        user_id,
                        game_session.id,
                    )
                    return False, "not_admin"

                await self._clear_old_timers(chat_id)

                if game_session.state != "waiting_players":
                    logger.info(
                        "Game was active, showing results for session %s",
                        game_session.id,
                    )

                    await self._update_player_stats(game_session.id)
                    await self._show_final_results(chat_id, game_session.id)

                    stop_message = (
                        f"🛑 *Игра досрочно завершена создателем!*\n\n"
                        f"🏁 Показаны финальные результаты.\n"
                        f"❓ Сыграно вопросов: "
                        f"{game_session.current_question_number - 1}/"
                        f"{game_session.total_questions}"
                    )
                    await self.app.store.telegram_api.send_message(
                        chat_id=chat_id, text=stop_message
                    )
                else:
                    await self.app.store.telegram_api.send_message(
                        chat_id=chat_id,
                        text="🛑 Игра в ожидании игроков отменена.",
                    )

                game_session.state = "finished"
                await session.commit()

                logger.info(
                    "Game stopped in chat %s by user %s", chat_id, user_id
                )
                return (
                    True,
                    "stopped"
                    if game_session.state != "waiting_players"
                    else "stopped",
                )

        except Exception:
            logger.exception("Error stopping game")
            return False, "error"

    async def get_global_leaderboard(self) -> str:
        """Возвращает глобальный топ игроков"""
        try:
            logger.info("Generating global leaderboard")

            async with self.app.store.database.session() as session:
                players_result = await session.execute(
                    select(Player)
                    .where(Player.games_played > 0)
                    .order_by(desc(Player.total_points))
                    .limit(10)
                )
                players = players_result.scalars().all()

                logger.info("Found %s players for leaderboard", len(players))

                if not players:
                    return "📊 Пока нет игроков в рейтинге.\n\nСыграйте первую игру, чтобы появиться в рейтинге!"

                message = "🏆 *ТОП ИГРОКОВ:*\n\n"

                for i, player in enumerate(players, 1):
                    # Экранируем специальные символы Markdown
                    username = player.username or f"игрок {player.telegram_id}"
                    safe_username = username.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')
                    
                    win_rate = (
                        (player.wins / player.games_played * 100)
                        if player.games_played > 0
                        else 0
                    )

                    message += (
                        f"{i}. *{safe_username}*\n"
                        f"   📊 Очков: `{player.total_points}`\n"
                        f"   🎮 Игр: `{player.games_played}`\n"
                        f"   🏆 Побед: `{player.wins}` ({win_rate:.1f}%)\n\n"
                    )

                message += "_Рейтинг обновляется после каждой игры_"
                
                logger.info("Global leaderboard generated successfully")
                return message

        except Exception as e:
            logger.exception("Error generating leaderboard: %s", str(e))
            return "❌ Ошибка при загрузке топа игроков\n\nПопробуйте позже."

    async def get_game_status(self, chat_id: int) -> str:
        """Возвращает статус текущей игры"""
        try:
            logger.info("Getting game status for chat %s", chat_id)

            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state.in_(
                            [
                                "waiting_players",
                                "question_start",
                                "accepting_answers",
                                "showing_results",
                                "round_transition",
                            ]
                        ),
                    )
                )
                game_session_row = game_session_result.first()

                if not game_session_row:
                    return "ℹ️ В этом чате нет активной игры."

                game_session = game_session_row[0]

                players_result = await session.execute(
                    select(SessionPlayer).where(
                        SessionPlayer.session_id == game_session.id
                    )
                )
                players = players_result.scalars().all()

                state_names = {
                    "waiting_players": "⏳ Ожидание игроков",
                    "question_start": "🎯 Начало вопроса",
                    "accepting_answers": "✍️ Прием ответов",
                    "showing_results": "📊 Показ результатов",
                    "round_transition": "⚡ Ожидание решения",
                    "finished": "🏁 Завершена",
                }

                status = (
                    f"📊 *СТАТУС ИГРЫ:*\n\n"
                    f"• Состояние: {state_names.get(game_session.state, 
                                                    game_session.state)}\n"
                    f"• Игроков: {len(players)}\n"
                    f"• Вопрос: {game_session.current_question_number}/"
                    f"{game_session.total_questions}\n"
                    f"• Раунд: {game_session.current_question_round}\n"
                )

                if game_session.state != "waiting_players":
                    status += "\n*Текущие очки:*\n"
                    for session_player in sorted(
                        players,
                        key=lambda sp: sp.final_score,
                        reverse=True,
                    ):
                        player = session_player.player
                        username = (
                            player.username or f"игрок {player.telegram_id}"
                        )
                        status += (
                            f"• @{username}: "
                            f"{session_player.final_score} очков\n"
                        )

                logger.info("Status generated for chat %s", chat_id)
                return status

        except Exception:
            logger.exception("Error getting game status")
            return "❌ Ошибка при получении статуса"
