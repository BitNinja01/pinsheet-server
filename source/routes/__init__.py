def register_routes(app, limiter, csrf, User):
    from source.routes.auth import register_auth_routes
    from source.routes.dashboard import register_dashboard_routes
    from source.routes.rounds import register_rounds_routes
    from source.routes.courses import register_courses_routes
    from source.routes.settings import register_settings_routes
    from source.routes.stats import register_stats_routes
    from source.routes.admin import register_admin_routes

    register_auth_routes(app, limiter, User)
    register_dashboard_routes(app, limiter, csrf)
    register_rounds_routes(app, csrf)
    register_courses_routes(app, csrf)
    register_settings_routes(app, csrf)
    register_stats_routes(app)
    register_admin_routes(app, csrf)
