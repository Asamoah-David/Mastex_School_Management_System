# Browser E2E (Playwright)

**Safe by default:** uses `schoolms.settings_e2e` (SQLite file under `schoolms/`, ignored by git). Do not point this at production.

## Setup

```bash
pip install -r requirements-e2e.txt
python -m playwright install chromium
```

## Run

```bash
pytest e2e_tests
```

`pytest.ini` disables global `anyio` / `pytest-playwright` plugins if installed, because they can start an asyncio loop before Django’s test DB is ready (especially on Windows + Python 3.13).

## Writing tests

- List **ORM fixtures** (`e2e_school_admin`, etc.) **before** the `page` argument so Django runs DB setup before Playwright starts.

## Scope

Smoke tests cover `/health/`, home, login UI, bad password, school admin → school dashboard, superuser → main dashboard. Extend with new files under `e2e_tests/`.
