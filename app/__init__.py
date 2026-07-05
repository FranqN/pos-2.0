from flask import Flask
from .config import Config
from .extensions import db, login_manager, migrate
from .models import User
from .context import get_tenant_context


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"

    from .routes import register_blueprints
    from .routes.error_handlers import register_error_handlers

    register_blueprints(app)
    register_error_handlers(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_context():
        return get_tenant_context()

    return app

