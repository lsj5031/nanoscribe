"""Allow running migrations via: python -m app.db.migrate"""

from __future__ import annotations

import os
from pathlib import Path

from app.db.migrate import run_migrations


def main() -> None:
    data_dir = Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))
    db_path = data_dir / "nanoscribe.db"
    print(f"Running migrations on {db_path} ...")
    run_migrations(db_path)
    print("Migrations complete.")


if __name__ == "__main__":
    main()
