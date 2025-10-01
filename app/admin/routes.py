from app.admin.views import AdminLoginView, AdminCurrentView


def setup_admin_routes(app):
    app.router.add_view("/admin.login", AdminLoginView)
    app.router.add_view("/admin.current", AdminCurrentView)