from app.admin.views import AdminCurrentView, AdminLoginView


def setup_admin_routes(app):
    app.router.add_view("/admin.login", AdminLoginView)
    app.router.add_view("/admin.current", AdminCurrentView)
