from .base import *  # noqa: F403

DEBUG = bool_env("DJANGO_DEBUG", "DEBUG", default=True)  # noqa: F405

for local_host in ("localhost", "127.0.0.1"):
    if local_host not in ALLOWED_HOSTS:  # noqa: F405
        ALLOWED_HOSTS.append(local_host)  # noqa: F405

for local_origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
    if local_origin not in CORS_ALLOWED_ORIGINS:  # noqa: F405
        CORS_ALLOWED_ORIGINS.append(local_origin)  # noqa: F405
    if local_origin not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
        CSRF_TRUSTED_ORIGINS.append(local_origin)  # noqa: F405

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(  # noqa: F405
    "rest_framework.renderers.BrowsableAPIRenderer"
)
