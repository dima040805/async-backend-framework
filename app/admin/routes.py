from app.admin.views import (
    AdminCurrentView,
    AdminLoginView,
    AdminPlayersView,
    AdminQuestionDetailView,
    AdminQuestionsView,
    AdminSessionsView,
)


def setup_admin_routes(app):
    app.router.add_view("/admin.login", AdminLoginView)
    app.router.add_view("/admin.current", AdminCurrentView)
    app.router.add_view("/admin.sessions", AdminSessionsView)
    app.router.add_view("/admin.players", AdminPlayersView)
    app.router.add_view("/admin.questions", AdminQuestionsView)
    app.router.add_view("/admin.questions/{question_id}", AdminQuestionDetailView)