import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from common.management.commands.backup_database import backup_client


def parse_postgres_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise CommandError("--target-database-url must be a PostgreSQL URL.")
    return parsed


def is_configured_database(parsed):
    configured = settings.DATABASES["default"]
    return (
        (parsed.hostname or "").lower() == str(configured.get("HOST") or "").lower()
        and (parsed.port or 5432) == int(configured.get("PORT") or 5432)
        and parsed.path.strip("/") == str(configured.get("NAME") or "")
        and unquote(parsed.username or "") == str(configured.get("USER") or "")
    )


class Command(BaseCommand):
    help = "Restore an object-storage backup into an explicitly named non-production PostgreSQL database and validate it."

    def add_arguments(self, parser):
        parser.add_argument("--backup-key", required=True)
        parser.add_argument("--target-database-url", required=True)
        parser.add_argument("--confirm-restore", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_restore"]:
            raise CommandError("Restores are destructive. Re-run with --confirm-restore after checking the target URL.")
        target_url = options["target_database_url"]
        production_url = os.environ.get("DATABASE_URL", "")
        parsed = parse_postgres_url(target_url)
        if (production_url and target_url.rstrip("/") == production_url.rstrip("/")) or is_configured_database(parsed):
            raise CommandError("Refusing to restore over DATABASE_URL. Use an isolated restore-drill database.")
        temporary = tempfile.NamedTemporaryFile(prefix="purple-squad-restore-", suffix=".dump", delete=False)
        temporary.close()
        backup_path = Path(temporary.name)
        client = backup_client()
        try:
            client.download_file(settings.BACKUP_S3_BUCKET, options["backup_key"], str(backup_path))
            environment = os.environ.copy()
            if parsed.password:
                environment["PGPASSWORD"] = unquote(parsed.password)
            if "sslmode=" in parsed.query:
                environment["PGSSLMODE"] = "require"
            command = [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
                "--host",
                parsed.hostname,
                "--port",
                str(parsed.port or 5432),
                "--username",
                unquote(parsed.username or ""),
                "--dbname",
                parsed.path.strip("/"),
                str(backup_path),
            ]
            subprocess.run(command, check=True, env=environment, capture_output=True, text=True)
            with psycopg.connect(target_url) as restored:
                with restored.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM django_migrations")
                    migration_count = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM bookings_booking")
                    booking_count = cursor.fetchone()[0]
            if migration_count <= 0:
                raise CommandError("Restore validation failed: migration history is empty.")
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"pg_restore failed: {exc.stderr[-500:]}") from exc
        finally:
            backup_path.unlink(missing_ok=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Restore validated in isolated database: migrations={migration_count}, bookings={booking_count}"
            )
        )
