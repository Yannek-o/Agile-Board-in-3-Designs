"""Settings for the automated test suite."""

import os
import tempfile

from django.core.management.utils import get_random_secret_key

os.environ.setdefault("DJANGO_SECRET_KEY", get_random_secret_key())

from config.settings.base import *  # noqa: E402,F401,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="agile_board_test_media_"))  # noqa: F405
ATTACHMENT_VIRUS_SCAN = "disabled"
SITE_URL = "http://testserver"
LOGIN_FAILURE_LIMIT = 5
LOGIN_IP_FAILURE_LIMIT = 20
TRUST_X_FORWARDED_FOR = False
