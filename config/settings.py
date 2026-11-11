"""Configuración del proyecto mediante variables de entorno."""

from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import environ
from django.core.exceptions import ImproperlyConfigured
from django.utils.log import DEFAULT_LOGGING

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env.str("SECRET_KEY")
if not SECRET_KEY.strip():
    raise ImproperlyConfigured("SECRET_KEY debe contener una clave del entorno.")

DEBUG = env.bool("DEBUG")
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS", default=["localhost", "127.0.0.1"] if DEBUG else []
)
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS es obligatorio en producción.")

DATABASES = {"default": env.db("DATABASE_URL")}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise ImproperlyConfigured("DATABASE_URL debe apuntar a PostgreSQL.")
if not DATABASES["default"].get("NAME"):
    raise ImproperlyConfigured("DATABASE_URL debe indicar una base de datos.")

INSTALLED_APPS = [
    "config.apps.AdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "accounts.apps.AccountsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
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
                "accounts.context_processors.email_delivery",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
ACCOUNT_FORMS = {"login": "accounts.forms.LoginForm"}
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_SIGNUP_ENABLED = False
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_MAX_EMAIL_ADDRESSES = 1
ACCOUNT_CHANGE_EMAIL = False
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[Aprendo a mi Ritmo] "
ACCOUNT_LOGIN_ON_PASSWORD_RESET = False
ACCOUNT_SESSION_REMEMBER = False
ACCOUNT_LOGOUT_ON_GET = False
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "accounts:entry"
LOGOUT_REDIRECT_URL = "account_login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG

EMAIL_BACKEND = env.str(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)
if not DEBUG and EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
    raise ImproperlyConfigured("El correo por consola se utiliza solo en desarrollo.")

EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="webmaster@localhost")
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ImproperlyConfigured("Configura EMAIL_USE_TLS o EMAIL_USE_SSL, uno a la vez.")

SITE_URL = (
    env.str("SITE_URL", default="http://localhost:8000")
    if DEBUG
    else env.str("SITE_URL")
).rstrip("/")
site_origin = urlsplit(SITE_URL)
if (
    site_origin.scheme not in {"http", "https"}
    or not site_origin.hostname
    or site_origin.username is not None
    or site_origin.password is not None
    or site_origin.path
    or site_origin.query
    or site_origin.fragment
):
    raise ImproperlyConfigured("SITE_URL debe ser un origen HTTP o HTTPS válido.")
if not DEBUG and site_origin.scheme != "https":
    raise ImproperlyConfigured("SITE_URL debe usar HTTPS en producción.")

LOGGING = deepcopy(DEFAULT_LOGGING)
LOGGING["filters"]["invitation_tokens"] = {"()": "accounts.logging.InvitationTokenFilter"}
for log_handler in LOGGING["handlers"].values():
    log_handler["filters"] = ["invitation_tokens", *log_handler.get("filters", [])]
