FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

FROM dependencies AS test
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir -r requirements-dev.lock
COPY . .
ENV DJANGO_SETTINGS_MODULE=tests.settings
CMD ["pytest", "tests/unit", "tests/integration", "--cov=schoolmenu", "--cov-branch", "--cov-report=term-missing", "--cov-report=json"]

FROM dependencies AS runtime
ENV DATABASE_PATH=/data/schoolcafe.sqlite3
RUN groupadd --gid 10001 lunchbox && useradd --uid 10001 --gid lunchbox --no-create-home lunchbox \
    && mkdir /data && chown lunchbox:lunchbox /data
COPY schoolmenu ./schoolmenu
COPY manage.py ./
COPY scripts/entrypoint.sh /usr/local/bin/lunchbox-entrypoint
RUN chmod 755 /usr/local/bin/lunchbox-entrypoint \
    && DJANGO_SECRET_KEY=build-only-not-used-at-runtime python manage.py collectstatic --noinput
USER 10001:10001
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
ENTRYPOINT ["lunchbox-entrypoint"]
CMD ["gunicorn", "schoolmenu.config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "30", "--access-logfile", "-", "--access-logformat", "%(h)s %(t)s %(m)s %(s)s %(b)s", "--error-logfile", "-"]
