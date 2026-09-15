import os
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


def backup_client():
    required = {
        "BACKUP_S3_ENDPOINT_URL": settings.BACKUP_S3_ENDPOINT_URL,
        "BACKUP_S3_BUCKET": settings.BACKUP_S3_BUCKET,
        "BACKUP_S3_ACCESS_KEY_ID": settings.BACKUP_S3_ACCESS_KEY_ID,
        "BACKUP_S3_SECRET_ACCESS_KEY": settings.BACKUP_S3_SECRET_ACCESS_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise CommandError(f"Backup storage is not configured: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=settings.BACKUP_S3_ENDPOINT_URL,
        region_name=settings.BACKUP_S3_REGION,
        aws_access_key_id=settings.BACKUP_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.BACKUP_S3_SECRET_ACCESS_KEY,
    )


def postgres_environment(database_settings):
    environment = os.environ.copy()
    if database_settings.get("PASSWORD"):
        environment["PGPASSWORD"] = str(database_settings["PASSWORD"])
    sslmode = (database_settings.get("OPTIONS") or {}).get("sslmode")
    if sslmode:
        environment["PGSSLMODE"] = str(sslmode)
    return environment


def postgres_args(database_settings):
    args = []
    if database_settings.get("HOST"):
        args.extend(["--host", str(database_settings["HOST"])])
    if database_settings.get("PORT"):
        args.extend(["--port", str(database_settings["PORT"])])
    if database_settings.get("USER"):
        args.extend(["--username", str(database_settings["USER"])])
    return args


class Command(BaseCommand):
    help = "Create a custom-format PostgreSQL backup, upload it encrypted, and enforce retention."

    def handle(self, *args, **options):
        database = connection.settings_dict
        if "postgresql" not in database["ENGINE"]:
            raise CommandError("Production backups require PostgreSQL.")
        client = backup_client()
        created_at = timezone.now()
        object_key = created_at.strftime("postgres/%Y/%m/%d/purple-squad-%Y%m%dT%H%M%SZ.dump")
        temporary = tempfile.NamedTemporaryFile(prefix="purple-squad-backup-", suffix=".dump", delete=False)
        temporary.close()
        backup_path = Path(temporary.name)
        try:
            command = [
                "pg_dump",
                *postgres_args(database),
                "--format=custom",
                "--compress=9",
                "--no-owner",
                "--no-acl",
                "--file",
                str(backup_path),
                str(database["NAME"]),
            ]
            subprocess.run(command, check=True, env=postgres_environment(database), capture_output=True, text=True)
            if backup_path.stat().st_size == 0:
                raise CommandError("pg_dump produced an empty backup.")
            client.upload_file(
                str(backup_path),
                settings.BACKUP_S3_BUCKET,
                object_key,
                ExtraArgs={
                    "ServerSideEncryption": "AES256",
                    "ContentType": "application/octet-stream",
                    "Metadata": {"database": str(database["NAME"]), "created-at": created_at.isoformat()},
                },
            )
            self._prune(client, created_at - timedelta(days=settings.BACKUP_RETENTION_DAYS))
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"pg_dump failed: {exc.stderr[-500:]}") from exc
        finally:
            backup_path.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Backup uploaded: {object_key}"))

    def _prune(self, client, cutoff):
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.BACKUP_S3_BUCKET, Prefix="postgres/"):
            expired = [
                {"Key": item["Key"]}
                for item in page.get("Contents", [])
                if item.get("LastModified") and item["LastModified"] < cutoff
            ]
            if expired:
                client.delete_objects(Bucket=settings.BACKUP_S3_BUCKET, Delete={"Objects": expired, "Quiet": True})
