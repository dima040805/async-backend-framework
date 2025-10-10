import base64

from aiohttp_apispec import docs, request_schema, response_schema
from aiohttp_session import get_session, new_session

from app.admin.schema import (
    AdminLoginSchema,
    PlayerListSchema,
    QuestionCreateSchema,
    QuestionListSchema,
    QuestionSchema,
    SessionListSchema,
)
from app.web.app import View
from app.web.schemes import OkResponseSchema
from app.web.utils import error_json_response, json_response


class AdminLoginView(View):
    @docs(tags=["admin"], summary="Зайти как админ", description="Зайти как админ")
    @request_schema(AdminLoginSchema)
    @response_schema(OkResponseSchema, 200)
    async def post(self):
        try:
            admin = await self.store.admin_accessor.authenticate_admin(
                self.data["email"], self.data["password"]
            )
            
            if not admin:
                return error_json_response(401, "unauthorized", "Invalid credentials")

            # Создаем сессию
            session_data = f"admin {admin.id}"
            encoded_auth = base64.b64encode(session_data.encode()).decode()
            
            session = await new_session(request=self.request)
            session["admin_auth"] = encoded_auth
            session["admin_id"] = admin.id

            return json_response(data={
                "message": "Login successful",
                "admin": {
                    "id": admin.id,
                    "email": admin.email,
                    "permissions": admin.permissions
                }
            })
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))


class AdminCurrentView(View):
    @docs(tags=["admin"], summary="Получить информацию о текущем админе", description="Получиить информацию об админе")
    @response_schema(OkResponseSchema, 200)
    async def get(self):
        try:
            session = await get_session(self.request)
            admin_id = session.get("admin_id")
            
            if not admin_id:
                return error_json_response(401, "unauthorized", "Not authenticated")

            admin = await self.store.admin_accessor.get_admin_by_id(admin_id)
            if not admin:
                return error_json_response(401, "unauthorized", "Admin not found")

            return json_response(data={
                "admin": {
                    "id": admin.id,
                    "email": admin.email,
                    "permissions": admin.permissions,
                    "is_active": admin.is_active
                }
            })
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))


class AdminSessionsView(View):
    @docs(tags=["admin"], summary="Получить все игровые сессии", description="Все игровые сессии")
    @response_schema(SessionListSchema, 200)
    async def get(self):
        try:
            await self._check_admin_auth()
            
            sessions = await self.store.admin_accessor.get_all_game_sessions()
            sessions_data = []
            
            for session in sessions:
                players_count = await self.store.admin_accessor.get_session_players_count(session.id)
                sessions_data.append({
                    "id": session.id,
                    "chat_id": session.chat_id,
                    "state": session.state,
                    "total_questions": session.total_questions,
                    "current_question_number": session.current_question_number,
                    "players_count": players_count,
                    "created_at": session.created_at.isoformat()
                })

            return json_response(data={
                "amount": len(sessions_data),
                "sessions": sessions_data
            })
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))


class AdminPlayersView(View):
    @docs(tags=["admin"], summary="Получить топ игроков", description="Топ игроков")
    @response_schema(PlayerListSchema, 200)
    async def get(self):
        try:
            await self._check_admin_auth()
            
            players = await self.store.admin_accessor.get_top_players(limit=100)
            players_data = []
            
            for player in players:
                players_data.append({
                    "id": player.id,
                    "telegram_id": player.telegram_id,
                    "username": player.username or f"player_{player.telegram_id}",
                    "games_played": player.games_played,
                    "wins": player.wins,
                    "total_points": player.total_points,
                    "rating": player.rating
                })

            return json_response(data={
                "amount": len(players_data),
                "players": players_data
            })
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))


class AdminQuestionsView(View):
    @docs(tags=["admin"], summary="Получить список вопросов", description="Посмотреть список вопросов")
    @response_schema(QuestionListSchema, 200)
    async def get(self):
        try:
            await self._check_admin_auth()
            
            questions = await self.store.admin_accessor.get_all_questions()
            questions_data = []
            
            for question in questions:
                questions_data.append({
                    "id": question.id,
                    "text": question.text,
                    "is_active": question.is_active
                })

            return json_response(data={
                "amount": len(questions_data),
                "questions": questions_data
            })
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))

    @docs(tags=["admin"], summary="Создать новый вопрос", description="Создание нового вопроса")
    @request_schema(QuestionCreateSchema)
    @response_schema(QuestionSchema, 201)
    async def post(self):
        try:
            await self._check_admin_auth()
            
            question = await self.store.admin_accessor.create_question(
                text=self.data["text"],
                is_active=self.data.get("is_active", True)
            )
            
            if not question:
                return error_json_response(400, "bad_request", "Failed to create question")

            return json_response(data={
                "id": question.id,
                "text": question.text,
                "is_active": question.is_active
            }, status=201)
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))


class AdminQuestionDetailView(View):
    @docs(tags=["admin"], summary="Обновить статус вопроса", description="Обновить статус вопроса")
    async def patch(self):
        try:
            await self._check_admin_auth()
            
            question_id = int(self.request.match_info["question_id"])
            is_active = self.data.get("is_active")
            
            if is_active is None:
                return error_json_response(400, "bad_request", "is_active field required")

            success = await self.store.admin_accessor.update_question_status(
                question_id, is_active
            )
            
            if not success:
                return error_json_response(404, "not_found", "Question not found")

            return json_response(data={"message": "Question updated successfully"})
            
        except Exception as e:
            return error_json_response(500, "internal_error", str(e))

    async def _check_admin_auth(self):
        """Проверка аутентификации админа"""
        session = await get_session(self.request)
        admin_id = session.get("admin_id")
        
        if not admin_id:
            raise PermissionError("Not authenticated")
        
        admin = await self.store.admin_accessor.get_admin_by_id(admin_id)
        if not admin:
            raise PermissionError("Admin not found")
        
        return admin