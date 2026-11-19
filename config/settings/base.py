"""Shared Django settings for all environments."""

from pathlib import Path

from config import env

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env.load_env_file(BASE_DIR / ".env")

SECRET_KEY = env.get_str("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.get_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.get_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.projects",
    "apps.backlog",
    "apps.sprints",
    "apps.board",
    "apps.reporting",
    "apps.activity",
    "apps.notifications",
    "apps.poker",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.navigation",
                "apps.core.context_processors.brand",
                "apps.notifications.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.get_str("POSTGRES_DB", "agile_board"),
        "USER": env.get_str("POSTGRES_USER", "agile_board"),
        "PASSWORD": env.get_str("POSTGRES_PASSWORD", ""),
        "HOST": env.get_str("POSTGRES_HOST", "localhost"),
        "PORT": env.get_str("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": env.get_int("POSTGRES_CONN_MAX_AGE", 60),
        "ATOMIC_REQUESTS": True,
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation."
        "NumericPasswordValidator"
    },
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "reporting:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
BRAND_LOGO_DIR = BASE_DIR / "static" / "img" / "brand"

# Uploaded files are only served through permission-checked views.
MEDIA_ROOT = Path(env.get_str("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
ATTACHMENT_MAX_UPLOAD_BYTES = env.get_int(
    "ATTACHMENT_MAX_UPLOAD_BYTES", 10 * 1024 * 1024
)
ATTACHMENT_ALLOWED_EXTENSIONS = [
    "pdf", "png", "jpg", "jpeg", "gif", "txt", "csv", "md", "log",
    "docx", "xlsx", "pptx", "zip", "json",
]
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Public base URL used for links in e-mails, e.g. https://agile.example.com
SITE_URL = env.get_str("SITE_URL", "http://localhost:8000")

EMAIL_BACKEND = env.get_str(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = env.get_str("EMAIL_HOST", "localhost")
EMAIL_PORT = env.get_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env.get_str("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env.get_str("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env.get_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env.get_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = env.get_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env.get_str(
    "DEFAULT_FROM_EMAIL", "Agile Board <agile-board@localhost>"
)
PASSWORD_RESET_TIMEOUT = env.get_int("PASSWORD_RESET_TIMEOUT", 2 * 60 * 60)
INVITATION_TIMEOUT = env.get_int("INVITATION_TIMEOUT", 7 * 24 * 60 * 60)

# Login throttling (see apps/accounts/throttling.py)
LOGIN_FAILURE_LIMIT = env.get_int("LOGIN_FAILURE_LIMIT", 5)
LOGIN_IP_FAILURE_LIMIT = env.get_int("LOGIN_IP_FAILURE_LIMIT", 20)
LOGIN_LOCKOUT_MINUTES = env.get_int("LOGIN_LOCKOUT_MINUTES", 15)
PASSWORD_RESET_IP_LIMIT = env.get_int("PASSWORD_RESET_IP_LIMIT", 5)
# Only enable behind a reverse proxy that overwrites X-Forwarded-For.
TRUST_X_FORWARDED_FOR = env.get_bool("TRUST_X_FORWARDED_FOR", False)

# Virus scanning of uploads: "disabled" or "clamav"
ATTACHMENT_VIRUS_SCAN = env.get_str("ATTACHMENT_VIRUS_SCAN", "disabled")
ATTACHMENT_SCAN_FAIL_CLOSED = env.get_bool("ATTACHMENT_SCAN_FAIL_CLOSED", True)
CLAMAV_HOST = env.get_str("CLAMAV_HOST", "127.0.0.1")
CLAMAV_PORT = env.get_int("CLAMAV_PORT", 3310)
CLAMAV_TIMEOUT = env.get_int("CLAMAV_TIMEOUT", 30)

# Polling interval of the live Agile Board in seconds
BOARD_POLL_INTERVAL_SECONDS = env.get_int("BOARD_POLL_INTERVAL_SECONDS", 10)

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 10
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

MESSAGE_TAGS = {40: "danger"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}
