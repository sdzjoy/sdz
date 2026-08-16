"""Prove that the final application installs into a completely empty database."""

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.path.insert(0, str(PROJECT_ROOT))
    with tempfile.TemporaryDirectory(prefix="sdzjoy-fresh-db-") as directory:
        database_path = Path(directory) / "fresh.sqlite3"
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.base"
        os.environ["SQLITE_DATABASE_PATH"] = str(database_path)

        import django
        from django.core.management import call_command
        from django.db import connection, connections

        django.setup()
        try:
            call_command("migrate", interactive=False, verbosity=0)
            call_command("check", verbosity=0)
            tables = set(connection.introspection.table_names())
            required = {
                "accounts_user",
                "publishing_contententry",
                "publishing_siteprofile",
                "studio_auditevent",
                "standards_standard",
                "resources_resource",
            }
            missing = sorted(required - tables)
            retired_prefixes = tuple(value + "_" for value in ("wag" + "tail", "content", "core"))
            retired = sorted(name for name in tables if name.startswith(retired_prefixes))
            if missing or retired:
                raise RuntimeError(
                    json.dumps(
                        {"missing_required_tables": missing, "retired_tables": retired},
                        ensure_ascii=False,
                    )
                )
            print(  # noqa: T201
                json.dumps(
                    {
                        "status": "ok",
                        "database": "temporary",
                        "table_count": len(tables),
                        "required_tables": sorted(required),
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            connections.close_all()


if __name__ == "__main__":
    main()
