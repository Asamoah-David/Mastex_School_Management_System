# Smoke tests (pytest + Django test client)

**Safe by default:** uses `schoolms.settings_e2e` (SQLite file under `schoolms/`, ignored by git). Do not point this at production.

CI runs these tests with **no browser** (stable on GitHub Actions). They hit `/health/`, home, login, and POST login with the same redirects a user would get.

## Setup

```bash
pip install "pytest>=8.0,<9" "pytest-django>=4.8,<5"
```

(Optionally `pip install -r requirements-e2e.txt` if you also use Playwright elsewhere.)

## Run

```bash
pytest e2e_tests
```

`pytest.ini` disables global `anyio` / `pytest-playwright` plugins if installed, because they can start an asyncio loop before Django’s test DB is ready (especially on Windows + Python 3.13).

## Optional Playwright

For real browser automation locally, install Chromium via `requirements-e2e.txt` and `python -m playwright install chromium`, then add separate tests/fixtures as needed.
