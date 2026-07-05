import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(os.path.abspath(os.path.dirname(__file__)), "pos.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(os.path.abspath(os.path.dirname(__file__)), "static", "uploads"),
    )
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

    # Basic multi-tenancy: all core pages operate under a tenant selected from URL or session.
    DEFAULT_TENANT_ID = None

