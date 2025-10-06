import asyncio
import typing
import datetime
from sqlalchemy import select, func, and_
from app.store.database.base_accessor import BaseAccessor
from app.models.database import (
    GameSession, Player, SessionPlayer, Question, 
    AnswerVariant, PlayerAnswer
)

if typing.TYPE_CHECKING:
    from app.web.app import Application

class GameAccessor(BaseAccessor):
    def __init__(self, app: "Application"):
        super().__init__(app)
        self.active_timers = {}

    def _normalize_answer(self, text: str) -> str:
        if not text:
            return ""
        normalized = text.lower().strip()
        normalized = ' '.join(normalized.split())
        return normalized

    async def create_session(self, chat_id: int, creator_telegram_id: int, username: str = None) -> GameSession:
        async with self.app.store.database.session() as session:
            existing_session = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers', 'showing_results', 'round_transition'])
                )
            )
            if existing_session.first():
                return None

            player = await session.execute(
                select(Player).where(Player.telegram_id == creator_telegram_id)
            )
            player = player.scalar_one_or_none()
            
            if not player:
                player = Player(
                    telegram_id=creator_telegram_id,
                    username=username,
                    first_name=username or "Player"
                )
                session.add(player)
                await session.commit()
                await session.refresh(player)

            game_session = GameSession(
                chat_id=chat_id,
                state='waiting_players',
                max_rounds_per_question=3
            )
            session.add(game_session)
            await session.commit()
            await session.refresh(game_session)

            session_player = SessionPlayer(
                player_id=player.id,
                session_id=game_session.id,
                is_admin=True
            )
            session.add(session_player)
            await session.commit()
            
            asyncio.create_task(self._waiting_players_timer(chat_id, 60))
            
            return game_session

    async def _waiting_players_timer(self, chat_id: int, duration: int):
        try:
            await asyncio.sleep(duration)
            
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
                    
                    if players_count >= 2:
                        success = await self._start_first_question(chat_id)
                        if success:
                            await self.app.store.telegram_api.send_message(
                                chat_id=chat_id, 
                                text="Время вышло! Игра начинается автоматически!"
                            )
                        else:
                            await self.app.store.telegram_api.send_message(
                                chat_id=chat_id, 
                                text="Не удалось начать игру."
                            )
                    else:
                        game_session.state = 'finished'
                        await session.commit()
                        
                        await self.app.store.telegram_api.send_message(
                            chat_id=chat_id, 
                            text="Время вышло! Недостаточно игроков для старта. Игра отменена."
                        )
                        
        except Exception:
            pass

    async def _start_first_question(self, chat_id: int) -> bool:
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

            players_count_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players_count = len(players_count_result.scalars().all())
            
            if players_count < 2:
                return False

            question = await self._get_random_question(session)
            if not question:
                return False

            game_session.state = 'question_start'
            game_session.current_question_number = 1
            game_session.current_question_round = 1
            game_session.current_question_id = question.id
            await session.commit()

            await self._send_question_to_chat(chat_id, question, 1, 1)
            
            game_session.state = 'accepting_answers'
            await session.commit()

            asyncio.create_task(self._round_timer(chat_id, 45))
            
            return True

    async def _send_question_to_chat(self, chat_id: int, question: Question, question_number: int, round_number: int):
        try:
            message = (
                f"ВОПРОС №{question_number} | РАУНД {round_number}\n\n"
                f"{question.text}\n\n"
                f"Правила:\n"
                f"• Присылайте свои ответы в чат\n"  
                f"• Каждый игрок может дать только 1 ответ за раунд\n"
                f"• Ответы принимаются 45 секунд\n"
                f"• Угадывайте самые популярные ответы!\n\n"
                f"Время пошло!"
            )
            
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=message)
        except Exception:
            pass

    async def _round_timer(self, chat_id: int, duration: int):
        try:
            await asyncio.sleep(duration - 10)
            
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == 'accepting_answers'
                    )
                )
                if game_session_result.first():
                    await self.app.store.telegram_api.send_message(
                        chat_id=chat_id, 
                        text="Осталось 10 секунд!"
                    )
            
            await asyncio.sleep(10)
            
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == 'accepting_answers'
                    )
                )
                game_session_row = game_session_result.first()
                
                if game_session_row:
                    await self._finish_round(chat_id)
                    
        except Exception:
            pass

    async def _check_all_players_answered(self, chat_id: int) -> bool:
        async with self.app.store.database.session() as session:
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

            players_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players = players_result.scalars().all()
            
            answers_result = await session.execute(
                select(PlayerAnswer).where(
                    PlayerAnswer.session_id == game_session.id,
                    PlayerAnswer.round == game_session.current_question_round
                )
            )
            answered_players = answers_result.scalars().all()
            
            return len(players) == len(answered_players)

    async def _get_already_revealed_variants(self, session, game_session_id: int, question_id: int) -> list:
        answers_result = await session.execute(
            select(PlayerAnswer).where(
                PlayerAnswer.session_id == game_session_id,
                PlayerAnswer.question_id == question_id
            )
        )
        all_answers = answers_result.scalars().all()
        
        variants_result = await session.execute(
            select(AnswerVariant).where(AnswerVariant.question_id == question_id)
        )
        all_variants = variants_result.scalars().all()
        
        revealed_variant_ids = []
        
        for variant in all_variants:
            for answer in all_answers:
                if answer.normalized_text == variant.text.lower():
                    revealed_variant_ids.append(variant.id)
                    break
        
        return revealed_variant_ids

    async def _finish_round(self, chat_id: int):
        try:
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == 'accepting_answers'
                    )
                )
                game_session_row = game_session_result.first()
                
                if not game_session_row:
                    return
                    
                game_session = game_session_row[0]

                already_revealed = await self._get_already_revealed_variants(
                    session, game_session.id, game_session.current_question_id
                )
                
                answers_result = await session.execute(
                    select(PlayerAnswer).where(
                        PlayerAnswer.session_id == game_session.id,
                        PlayerAnswer.round == game_session.current_question_round
                    )
                )
                answers = answers_result.scalars().all()

                variants_result = await session.execute(
                    select(AnswerVariant).where(
                        AnswerVariant.question_id == game_session.current_question_id
                    ).order_by(AnswerVariant.position)
                )
                all_variants = variants_result.scalars().all()

                round_scored_variants = []
                newly_revealed = []
                
                for variant in all_variants:
                    if variant.id in already_revealed:
                        continue
                        
                    variant_answers = []
                    
                    for answer in answers:
                        if answer.normalized_text == variant.text.lower():
                            player_result = await session.execute(
                                select(Player).where(Player.id == answer.player_id)
                            )
                            player = player_result.scalar_one()
                            
                            variant_answers.append({
                                'player_id': player.id,
                                'telegram_id': player.telegram_id,
                                'username': player.username,
                                'answer_id': answer.id
                            })
                    
                    if variant_answers:
                        round_scored_variants.append({
                            'variant': variant,
                            'answers': variant_answers
                        })
                        newly_revealed.append(variant.id)
                        
                        points_per_player = variant.points // len(variant_answers)
                        
                        for answer_info in variant_answers:
                            answer_update = await session.execute(
                                select(PlayerAnswer).where(PlayerAnswer.id == answer_info['answer_id'])
                            )
                            player_answer = answer_update.scalar_one()
                            player_answer.points_earned = points_per_player
                            
                            session_player_update = await session.execute(
                                select(SessionPlayer).where(
                                    SessionPlayer.player_id == answer_info['player_id'],
                                    SessionPlayer.session_id == game_session.id
                                )
                            )
                            session_player = session_player_update.scalar_one()
                            session_player.final_score += points_per_player

                game_session.state = 'showing_results'
                await session.commit()

                all_revealed_now = already_revealed + newly_revealed
                await self._show_round_results(chat_id, round_scored_variants, game_session, all_revealed_now)
                
                all_variants_revealed = len(all_revealed_now) == len(all_variants)
                max_rounds_reached = game_session.current_question_round >= game_session.max_rounds_per_question
                
                if all_variants_revealed or max_rounds_reached:
                    await self._finish_question(chat_id)
                else:
                    game_session.state = 'round_transition'
                    await session.commit()
                    await self._ask_admin_decision(chat_id, game_session)
                        
        except Exception:
            pass

    async def _show_round_results(self, chat_id: int, scored_variants: list, game_session: GameSession, all_revealed_variants: list):
        try:
            async with self.app.store.database.session() as session:
                variants_result = await session.execute(
                    select(AnswerVariant).where(
                        AnswerVariant.question_id == game_session.current_question_id
                    ).order_by(AnswerVariant.position)
                )
                all_variants = variants_result.scalars().all()

                message = "Результаты раунда:\n\n"
                
                revealed_count = 0
                current_round_revealed = 0
                
                for variant in all_variants:
                    if variant.id in all_revealed_variants:
                        revealed_count += 1
                        
                        answers_result = await session.execute(
                            select(PlayerAnswer, Player).join(Player).where(
                                PlayerAnswer.session_id == game_session.id,
                                PlayerAnswer.question_id == game_session.current_question_id,
                                PlayerAnswer.normalized_text == variant.text.lower()
                            )
                        )
                        answers_with_players = answers_result.all()
                        
                        players_list = []
                        for answer, player in answers_with_players:
                            username = player.username or f"игрок {player.telegram_id}"
                            players_list.append(f"@{username}")
                        
                        players_str = ", ".join(players_list) if players_list else "—"
                        
                        if variant.id in [v['variant'].id for v in scored_variants]:
                            current_round_revealed += 1
                        
                        message += f"{variant.position}. *{variant.text}* - {variant.points} очков ({players_str})\n"
                    else:
                        message += f"{variant.position}. —\n"
                
                message += f"\nОткрыто вариантов: {revealed_count}/{len(all_variants)}"
                message += f"\nВ этом раунде угадано: {current_round_revealed} новых ответов"
                
                await self.app.store.telegram_api.send_message(chat_id=chat_id, text=message)
                    
        except Exception:
            pass

    async def _ask_admin_decision(self, chat_id: int, game_session: GameSession):
        try:
            message = (
                f"Вопрос {game_session.current_question_number} | Раунд {game_session.current_question_round} завершен!\n\n"
                f"Что делаем дальше?\n\n"
                f"'Продолжить угадывать' - начать следующий раунд с этим же вопросом\n"
                f"'Следующий вопрос' - перейти к следующему вопросу\n\n"
                f"Создатель игры, выберите действие:"
            )
            
            await self.app.store.telegram_api.send_message(chat_id=chat_id, text=message)
            
        except Exception:
            pass

    async def continue_guessing(self, chat_id: int, admin_telegram_id: int) -> bool:
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == 'round_transition'
                )
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False
                
            game_session = game_session_row[0]
            
            is_admin = await self._check_admin_rights(session, game_session.id, admin_telegram_id)
            if not is_admin:
                return False
            
            game_session.current_question_round += 1
            game_session.state = 'accepting_answers'
            await session.commit()
            
            question_result = await session.execute(
                select(Question).where(Question.id == game_session.current_question_id)
            )
            question = question_result.scalar_one()
            
            await self._send_question_to_chat(
                chat_id, question, 
                game_session.current_question_number, 
                game_session.current_question_round
            )
            
            asyncio.create_task(self._round_timer(chat_id, 45))
            
            return True

    async def next_question(self, chat_id: int, admin_telegram_id: int) -> bool:
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state == 'round_transition'
                )
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False
                
            game_session = game_session_row[0]

            is_admin = await self._check_admin_rights(session, game_session.id, admin_telegram_id)
            if not is_admin:
                return False
            
            game_session.current_question_number += 1
            game_session.current_question_round = 1
            
            if game_session.current_question_number > game_session.total_questions:
                await self._finish_game(chat_id, game_session)
                return True
            
            question = await self._get_random_question(session)
            if not question:
                return False
                
            game_session.current_question_id = question.id
            game_session.state = 'accepting_answers'
            await session.commit()
            
            await self._send_question_to_chat(
                chat_id, question, 
                game_session.current_question_number, 
                game_session.current_question_round
            )
            
            asyncio.create_task(self._round_timer(chat_id, 45))
            
            return True

    async def _finish_game(self, chat_id: int, game_session: GameSession):
        try:
            await self._update_player_stats(game_session.id)
            await self._show_final_results(chat_id, game_session.id)
            game_session.state = 'finished'
            async with self.app.store.database.session() as session:
                session.add(game_session)
                await session.commit()
                
        except Exception:
            pass

    async def _finish_question(self, chat_id: int):
        try:
            async with self.app.store.database.session() as session:
                game_session_result = await session.execute(
                    select(GameSession).where(
                        GameSession.chat_id == chat_id,
                        GameSession.state == 'showing_results'
                    )
                )
                game_session_row = game_session_result.first()
                
                if not game_session_row:
                    return
                    
                game_session = game_session_row[0]
                
                game_session.current_question_number += 1
                game_session.current_question_round = 1
                
                if game_session.current_question_number > game_session.total_questions:
                    await self._finish_game(chat_id, game_session)
                    return
                
                question = await self._get_random_question(session)
                if not question:
                    game_session.state = 'finished'
                    await session.commit()
                    await self.app.store.telegram_api.send_message(
                        chat_id=chat_id, 
                        text="Не удалось найти следующий вопрос. Игра завершена."
                    )
                    return
                    
                game_session.current_question_id = question.id
                game_session.state = 'accepting_answers'
                await session.commit()
                
                await self._send_question_to_chat(
                    chat_id, question, 
                    game_session.current_question_number, 
                    game_session.current_question_round
                )
                
                asyncio.create_task(self._round_timer(chat_id, 45))
                
        except Exception:
            pass

    async def _update_player_stats(self, session_id: int):
        async with self.app.store.database.session() as session:
            players_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == session_id)
            )
            session_players = players_result.scalars().all()
            
            for session_player in session_players:
                player = session_player.player
                player.games_played += 1
                player.total_points += session_player.final_score
                player.date_last_game = datetime.datetime.utcnow()
                session.add(player)
            
            await session.commit()

    async def _show_final_results(self, chat_id: int, session_id: int):
        try:
            async with self.app.store.database.session() as session:
                players_result = await session.execute(
                    select(SessionPlayer)
                    .where(SessionPlayer.session_id == session_id)
                    .order_by(SessionPlayer.final_score.desc())
                )
                session_players = players_result.scalars().all()
                
                message = "ФИНАЛЬНЫЕ РЕЗУЛЬТАТЫ ИГРЫ:\n\n"
                
                for i, session_player in enumerate(session_players, 1):
                    player = session_player.player
                    username = player.username or f"игрок {player.telegram_id}"
                    message += f"{i}. @{username} - {session_player.final_score} очков\n"
                
                message += "\nСпасибо за игру!"
                
                await self.app.store.telegram_api.send_message(chat_id=chat_id, text=message)
                
        except Exception:
            pass

    async def _check_admin_rights(self, session, session_id: int, telegram_id: int) -> bool:
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
                SessionPlayer.is_admin == True
            )
        )
        
        return admin_check.first() is not None

    async def _get_random_question(self, session) -> Question:
        question_result = await session.execute(
            select(Question).where(Question.is_active == True).order_by(func.random()).limit(1)
        )
        return question_result.scalar_one_or_none()

    async def add_player_to_session(self, chat_id: int, telegram_id: int, username: str = None) -> tuple:
        async with self.app.store.database.session() as session:
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

            player_result = await session.execute(
                select(Player).where(Player.telegram_id == telegram_id)
            )
            player = player_result.scalar_one_or_none()
            
            if not player:
                player = Player(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=username or "Player"
                )
                session.add(player)
                await session.commit()
                await session.refresh(player)

            existing_player_result = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.player_id == player.id,
                    SessionPlayer.session_id == game_session.id
                )
            )
            if existing_player_result.first():
                return False, "already_joined"

            session_player = SessionPlayer(
                player_id=player.id,
                session_id=game_session.id,
                is_admin=False
            )
            session.add(session_player)
            await session.commit()

            players_count_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players_count = len(players_count_result.scalars().all())
            
            if players_count >= 8:
                success = await self._start_first_question(chat_id)
                if success:
                    return True, "auto_started"
            
            return True, "joined"

    async def admin_start_game(self, chat_id: int, admin_telegram_id: int) -> tuple:
        async with self.app.store.database.session() as session:
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

            players_count_result = await session.execute(
                select(SessionPlayer).where(SessionPlayer.session_id == game_session.id)
            )
            players_count = len(players_count_result.scalars().all())
            
            if players_count < 2:
                return False, "not_enough_players"

            success = await self._start_first_question(chat_id)
            if success:
                return True, "started"
            else:
                return False, "start_failed"

    async def submit_answer(self, chat_id: int, telegram_id: int, answer_text: str) -> bool:
        async with self.app.store.database.session() as session:
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

            session_player_result = await session.execute(
                select(SessionPlayer).where(
                    SessionPlayer.player_id == player.id,
                    SessionPlayer.session_id == game_session.id
                )
            )
            if not session_player_result.first():
                return False

            existing_answer = await session.execute(
                select(PlayerAnswer).where(
                    PlayerAnswer.player_id == player.id,
                    PlayerAnswer.session_id == game_session.id,
                    PlayerAnswer.question_id == game_session.current_question_id,
                    PlayerAnswer.round == game_session.current_question_round
                )
            )
            if existing_answer.first():
                return False

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

            all_answered = await self._check_all_players_answered(chat_id)
            if all_answered:
                asyncio.create_task(self._finish_round(chat_id))

            return True

    async def stop_game(self, chat_id: int, user_id: int) -> tuple:
        async with self.app.store.database.session() as session:
            game_session_result = await session.execute(
                select(GameSession).where(
                    GameSession.chat_id == chat_id,
                    GameSession.state.in_(['waiting_players', 'question_start', 'accepting_answers', 'showing_results', 'round_transition'])
                ).order_by(GameSession.id.desc())
            )
            game_session_row = game_session_result.first()
            
            if not game_session_row:
                return False, "no_active_game"
            
            game_session = game_session_row[0]

            player_result = await session.execute(
                select(Player).where(Player.telegram_id == user_id)
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

            game_session.state = 'finished'
            await session.commit()

            return True, "stopped"