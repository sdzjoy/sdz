import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEVELOPMENT_SECRET_SENTINEL = "development-only-change-me"  # noqa: S105
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", DEVELOPMENT_SECRET_SENTINEL)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "accounts",
    "core",
    "content",
    "standards",
    "resources",
    "notifications",
    "searchapp",
    "operations",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.usersessions",
    "allauth.idp.oidc",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.contrib.table_block",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core.middleware.CanonicalHostMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "allauth.usersessions.middleware.UserSessionsMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.StaffMFARequiredMiddleware",
    "accounts.middleware.PrivateResponseMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
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
                "accounts.context_processors.security_settings",
                "core.context_processors.site_shell",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(
            os.getenv("SQLITE_DATABASE_PATH", BASE_DIR / "var" / "db.sqlite3")
        ),
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

WAGTAIL_SITE_NAME = "少惰主 · SDZJOY"
WAGTAILADMIN_BASE_URL = os.getenv("WAGTAILADMIN_BASE_URL", "http://localhost:8000")
WAGTAIL_I18N_ENABLED = False

PUBLIC_SITE_ORIGIN = os.getenv("PUBLIC_SITE_ORIGIN", "")
WWW_REDIRECT_HOST = os.getenv("WWW_REDIRECT_HOST", "")

# django-treebeard 5.3 added this forward-looking check before Wagtail's
# managers were updated. Wagtail maintainers confirm it is harmless on
# Wagtail 7.4.2 and will be resolved by the next release:
# https://github.com/wagtail/wagtail/issues/14487
SILENCED_SYSTEM_CHECKS = ["treebeard.E001"]

LOGIN_URL = "/account/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.forms.SignupExtraForm"
ACCOUNT_SIGNUP_FORM_HONEYPOT_FIELD = "website"
ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "mandatory")
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_CHANGE_EMAIL = True
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_REAUTHENTICATION_REQUIRED = True
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
ACCOUNT_SESSION_REMEMBER = False
ACCOUNT_RATE_LIMITS = {
    "login": "20/m/ip",
    "login_failed": "8/5m/ip,5/5m/key",
    "signup": "8/h/ip",
    "reset_password": "10/h/ip,5/h/key",
    "reauthenticate": "8/5m/user",
}
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[少惰主] "

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "少惰主 <noreply@sdzjoy.com>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

NOTIFICATION_WORKER_INTERVAL = int(os.getenv("NOTIFICATION_WORKER_INTERVAL", "30"))
CRITICAL_PATH_URLS = env_list(
    "CRITICAL_PATH_URLS",
    "/,/account/login/,/search/?q=GB,/standards/",
)

MFA_ADAPTER = "accounts.adapters.EncryptedMFAAdapter"
MFA_SUPPORTED_TYPES = ["totp", "webauthn", "recovery_codes"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_PASSKEY_SIGNUP_ENABLED = False
MFA_RECOVERY_CODES_SHOW_ONCE = True
MFA_TOTP_ISSUER = "少惰主 · SDZJOY"
MFA_TRUST_ENABLED = False
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", "")

USERSESSIONS_TRACK_ACTIVITY = True

IDP_OIDC_ADAPTER = "accounts.adapters.SDZJOYOIDCAdapter"
IDP_OIDC_PRIVATE_KEY = os.getenv("IDP_OIDC_PRIVATE_KEY", "").replace("\\n", "\n")
IDP_OIDC_AUTHORIZATION_CODE_EXPIRES_IN = 60
IDP_OIDC_ACCESS_TOKEN_EXPIRES_IN = 900
IDP_OIDC_ACCESS_TOKEN_FORMAT = "opaque"  # noqa: S105
IDP_OIDC_ROTATE_REFRESH_TOKEN = True
IDP_OIDC_DCR_ENABLED = False

TURNSTILE_REQUIRED = env_bool("TURNSTILE_REQUIRED", False)
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "")
TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "")
TURNSTILE_EXPECTED_HOSTNAMES = env_list("TURNSTILE_EXPECTED_HOSTNAMES")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
REFERRER_POLICY = "strict-origin-when-cross-origin"

DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
