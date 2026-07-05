from flask_migrate import Migrate
from app import create_app
from app.extensions import db

app = create_app()

# For `flask db` commands
migrate = Migrate(app, db)

if __name__ == "__main__":
    app.run(debug=True)

