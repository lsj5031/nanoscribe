"""Allow running migrations via: python -m app.db"""

from __future__ import annotations

from app.core.config import get_settings
from app.db.migrate import run_migrations


def main() -> None:
    settings = get_settings()
    db_path = settings.db_path
    print(f"Running migrations on {db_path} ...")
    run_migrations(db_path)
    print("Migrations complete.")


if __name__ == "__main__":
    main()
