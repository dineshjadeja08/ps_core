import os

import dj_database_url

from .base import *  # noqa: F403


DEBUG = False
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL must be set for the backup job.")
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=0,
        conn_health_checks=True,
    )
}
