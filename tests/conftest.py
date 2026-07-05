import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on PYTHONPATH so `import app` works when running pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db

# Import models so that SQLAlchemy metadata includes all tables
import app.models  # noqa: F401



@pytest.fixture(scope="session")
def temp_db_path():
    fd, path = tempfile.mkstemp(prefix="pos_test_", suffix=".db")
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture()
def app(temp_db_path):
    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{temp_db_path}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        LOGIN_DISABLED=False,
        # uploads not needed for tests
        UPLOAD_FOLDER=os.path.join(os.getcwd(), "static", "uploads_test"),
        DEFAULT_TENANT_ID=None,
        SECRET_KEY="test-secret",
    )

    # Ensure tables exist (fresh per app fixture)
    with app.app_context():
        db.drop_all()
        db.create_all()

    yield app

    # Cleanup tables after tests (best-effort)
    with app.app_context():
        db.drop_all()




@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def app_ctx(app):
    with app.app_context():
        yield
