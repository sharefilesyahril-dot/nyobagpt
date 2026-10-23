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

## Core Foundation handoff

See [HTTP API and Subsystem B contract](docs/core-foundation-api.md) for
routes, request/response fields, error codes, fake-action workflow, and
security limitations. The application records permissions and permits but
**never executes external actions**. Owner bootstrap uses the protected
service/CLI flow; no public HTTP bootstrap endpoint exists.

Use a disposable PostgreSQL 16 database for migrations and tests. To verify
from a clean database, run `alembic upgrade head`, `pytest -q -ra`, and
`ruff check .`. To test downgrade/upgrade, use another disposable database
and run `alembic downgrade base` followed by `alembic upgrade head`.
Do not run these commands against a production or Windows user database.
