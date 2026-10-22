# AI Agency Autopilot

The core service uses FastAPI and PostgreSQL for transactional workspace data.

## Local setup

Use Python 3.12 or newer and install the development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Set `DATABASE_URL` to a disposable PostgreSQL database. SQLite is deliberately
unsupported because transactional behavior is verified against PostgreSQL.

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/autopilot"
alembic upgrade head
pytest -v
ruff check .
```

Run the service with:

```powershell
uvicorn autopilot.app:app --reload
```

`GET /health` returns `{"status":"ok"}`.
