"""Runs a manage.py command against an embedded local PostgreSQL server.

Intended for development machines without a PostgreSQL installation.
Requires the optional dev dependency ``pgserver`` (see requirements-dev.txt).

Usage:
    python scripts/run_with_pg.py migrate
    python scripts/run_with_pg.py runserver
    python scripts/run_with_pg.py test --settings=config.settings.test
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(
    os.environ.get("AGILE_BOARD_PGDATA", BASE_DIR / ".pgdata")
).resolve()
DATABASE_NAME = os.environ.get("POSTGRES_DB", "agile_board")


def ensure_timezone_data(pgserver_module) -> None:
    """The Windows build of pgserver ships without IANA time zone files.

    PostgreSQL reads the same TZif format that the ``tzdata`` package provides,
    so the files are copied once into the server's share directory.
    """
    import shutil

    import tzdata

    share_dir = Path(pgserver_module.__file__).parent / "pginstall" / "share"
    target = share_dir / "postgresql" / "timezone"
    if target.is_dir():
        return
    source = Path(tzdata.__file__).parent / "zoneinfo"
    shutil.copytree(
        source, target, ignore=shutil.ignore_patterns("__init__.py", "__pycache__")
    )


def ensure_database(server_uri: str) -> None:
    """Creates the application database if it does not exist yet.

    Uses psycopg instead of ``pgserver``'s ``psql`` helper, which fails when
    the project path contains spaces.
    """
    import psycopg
    from psycopg import sql

    with psycopg.connect(server_uri, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE_NAME,)
        ).fetchone()
        if exists is None:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE_NAME))
            )


def main() -> int:
    try:
        import pgserver
    except ImportError:
        print("pgserver fehlt: pip install -r requirements-dev.txt", file=sys.stderr)
        return 1

    ensure_timezone_data(pgserver)
    server = pgserver.get_server(DATA_DIR, cleanup_mode=None)
    server_uri = server.get_uri()
    ensure_database(server_uri)

    uri = urlparse(server_uri)
    environment = os.environ.copy()
    environment.update(
        {
            "POSTGRES_DB": DATABASE_NAME,
            "POSTGRES_USER": uri.username or "postgres",
            "POSTGRES_PASSWORD": uri.password or "",
            "POSTGRES_HOST": uri.hostname or "127.0.0.1",
            "POSTGRES_PORT": str(uri.port or 5432),
        }
    )
    print(
        f"Embedded PostgreSQL: {environment['POSTGRES_HOST']}:"
        f"{environment['POSTGRES_PORT']} / {DATABASE_NAME}"
    )
    command = [sys.executable, str(BASE_DIR / "manage.py"), *sys.argv[1:]]
    return subprocess.call(command, env=environment, cwd=BASE_DIR)


if __name__ == "__main__":
    sys.exit(main())
