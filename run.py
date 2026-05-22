import os
from pathlib import Path

from flask_migrate import stamp as migrate_stamp, upgrade as migrate_upgrade
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from populate_data import populate

def _sqlite_path(app):
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
    db_path = _sqlite_path(app)

    if db_path and not db_path.exists():
        print(f"Database not found at {db_path}. Initializing sample data...")
        populate(app)
        return

    if db_path:
        print("Database ready.")
        return

    with app.app_context():
        inspector = inspect(db.engine)
        user_tables = set(inspector.get_table_names()) - {"alembic_version"}
        if user_tables:
            print("External database configured. Applying migrations...")
            migrate_upgrade()
            print("External database migrations applied.")
            return

        print("External database is empty. Creating schema...")
        db.create_all()
        migrate_stamp(revision="head")
        print("External database initialized.")


app = create_app()

prepare_database(app)

if __name__ == "__main__":
    host = app.config.get("HOST", "0.0.0.0")
    port = int(app.config.get("PORT", 5000))

    app.run(
        host=host,
        port=port,
        use_reloader=app.debug
    )
