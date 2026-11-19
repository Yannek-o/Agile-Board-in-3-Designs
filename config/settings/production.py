"""Production settings. All secrets must be provided by the environment."""

from django.core.exceptions import ImproperlyConfigured

from config import env
from config.settings.base import *  # noqa: F401,F403

DEBUG = False

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production.")

if len(SECRET_KEY) < 50:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be at least 50 characters.")

SECURE_SSL_REDIRECT = env.get_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.get_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
# Internal host names are not submitted to the public HSTS preload list.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Uploads are scanned by ClamAV unless explicitly disabled.
ATTACHMENT_VIRUS_SCAN = env.get_str("ATTACHMENT_VIRUS_SCAN", "clamav")

if not SITE_URL.startswith("https://"):  # noqa: F405
    raise ImproperlyConfigured("SITE_URL must be an https:// URL in production.")
