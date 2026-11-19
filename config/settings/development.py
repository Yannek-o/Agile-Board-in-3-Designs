"""Local development settings."""

from config import env
from config.settings.base import *  # noqa: F401,F403

DEBUG = env.get_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env.get_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
EMAIL_BACKEND = env.get_str(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)

LOGGING["root"]["level"] = "INFO"  # noqa: F405
