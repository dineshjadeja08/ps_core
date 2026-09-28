FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev postgresql-client curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "."

COPY . .

RUN DJANGO_SETTINGS_MODULE=config.settings.local SECRET_KEY=container-build-only python manage.py collectstatic --noinput \
    && chmod +x /app/scripts/render-start.sh /app/scripts/cloud-run-start.sh /app/scripts/cloud-run-migrate.sh \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["/app/scripts/cloud-run-start.sh"]
