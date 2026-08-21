# Purple Squad Backend

Production-oriented Django foundation for the Purple Squad home services platform.

## Stack

- Python 3.12+
- Django 5.2 LTS
- Django REST Framework
- PostgreSQL
- drf-spectacular
- pytest

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
docker compose up -d db
python manage.py migrate
python manage.py runserver
```

API documentation:

- Schema: `http://localhost:8000/api/schema/`
- Swagger UI: `http://localhost:8000/api/docs/`
- Redoc: `http://localhost:8000/api/redoc/`
- Health: `http://localhost:8000/api/v1/health/`

## Authentication

Phase 2 uses Firebase Phone Authentication as the identity proof and Purple Squad JWTs for API access.

- `POST /api/v1/auth/firebase/` verifies a Firebase ID token and returns `access` and `refresh` tokens.
- `POST /api/v1/auth/refresh/` returns a new access token.
- `GET /api/v1/auth/me/` returns the authenticated user.
- `POST /api/v1/auth/logout/` blacklists a refresh token.

Send authenticated API requests with:

```text
Authorization: Bearer <access-token>
```

## Checks

```powershell
python manage.py check
python manage.py spectacular --validate
pytest
```

## Deployment

Phase 13 deployment readiness targets Render with managed PostgreSQL.

- Deployment guide: `DEPLOYMENT.md`
- Render blueprint: `render.yaml`
- Production server: `gunicorn`
- Static files: WhiteNoise after `collectstatic`
- Health probe: `/api/v1/health/`

Production deploy checks:

```powershell
python manage.py check --deploy
python manage.py collectstatic --noinput
```

## Environment

Use `.env.example` as the template. Secrets must be supplied through environment variables and must not be committed.
