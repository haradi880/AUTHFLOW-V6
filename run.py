import os
from pathlib import Path

from app import create_app
from app.extensions import db
from populate_data import populate


def _sqlite_path(app):
    """Return the configured SQLite database path, if the app uses SQLite."""
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite:///"):
        return None

    raw_path = uri.replace("sqlite:///", "", 1)
    if raw_path == ":memory:":
        return None

    if os.name == "nt" and raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]

    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path(app.root_path).parent / db_path
    return db_path


def prepare_database(app):
    """Create missing tables and seed local SQLite only when the database is new."""
    db_path = _sqlite_path(app)
    is_new_local_db = bool(db_path and not db_path.exists())
    with app.app_context():
        db.create_all()
    if is_new_local_db:
        print(f"Database not found at {db_path}. Initializing sample data...")
        populate(app)
    else:
        print("Database ready." if db_path else "External database configured; tables checked.")

app = create_app()

prepare_database(app)

if __name__ == '__main__':
    host = app.config.get("HOST", "0.0.0.0")
    port = int(app.config.get("PORT", 5000))
    app.run(host=host, port=port, use_reloader=app.debug)
