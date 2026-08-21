from .base import *  # noqa: F403

DEBUG = env("DJANGO_DEBUG", default=True)  # noqa: F405

if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]  # noqa: F405

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(  # noqa: F405
    "rest_framework.renderers.BrowsableAPIRenderer"
)
