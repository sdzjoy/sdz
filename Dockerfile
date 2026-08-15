FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app

COPY requirements/base.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /tmp/requirements.txt

COPY --chown=app:app . /app

RUN mkdir -p /app/media /app/staticfiles /app/var \
    && chown -R app:app /app/media /app/staticfiles /app/var \
    && DJANGO_SECRET_KEY=build-only-not-for-runtime \
       DJANGO_ALLOWED_HOSTS=localhost \
       POSTGRES_PASSWORD=build-only-not-for-runtime \
       MFA_ENCRYPTION_KEY=build-only-not-for-runtime \
       IDP_OIDC_PRIVATE_KEY=build-only-not-for-runtime \
       TURNSTILE_SITE_KEY=build-only-not-for-runtime \
       TURNSTILE_SECRET_KEY=build-only-not-for-runtime \
       python manage.py collectstatic --noinput

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=3)"

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-", "--error-logfile", "-"]
