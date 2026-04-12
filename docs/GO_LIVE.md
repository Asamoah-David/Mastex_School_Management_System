# Go-live (what is already done vs what your host does)

The codebase side is wired for production: security headers when `DEBUG=False`, Paystack webhook verification, subscription middleware, multi-school scoping fixes, CI (Django tests + `preflight` + Playwright smoke tests), and `python manage.py preflight` for on-server checks.

## What you do on the hosting platform (once)

1. Copy variables from `.env.example` into your platform’s **environment** UI (Railway, Render, etc.). Set **`DEBUG=False`**, a strong **`SECRET_KEY`**, **`DATABASE_URL`** (PostgreSQL), **`ALLOWED_HOSTS`**, **`CSRF_TRUSTED_ORIGINS`**, and **`PAYSTACK_SECRET_KEY`** / **`PAYSTACK_PUBLIC_KEY`**. For Railway/Render/Fly, **`BEHIND_TLS_TERMINATING_PROXY`** is usually inferred; otherwise set it to `1`.
2. Set the Paystack **webhook URL** to `https://<your-domain>/finance/paystack-webhook/` (live mode, same secret key as API).
3. Deploy. Your pipeline should run **GitHub Actions CI** (or the same steps locally): `check --deploy`, `makemigrations --check`, `migrate`, `collectstatic`, `preflight`, `manage.py test`, `pytest e2e_tests`. Run **`migrate` before `preflight`** on each environment so migration checks pass (preflight reads the live database).
4. **`collectstatic`** output belongs in the runtime filesystem only; `schoolms/staticfiles/` is not committed — CI and your host generate it during deploy.
5. Optional SSH/console: `python manage.py preflight` — must exit **0** before you call the site “live”. Warnings for optional keys (SMS, Sentry, Paystack until configured) are normal.

No further repo steps are required for a standard PaaS deploy if CI is green.
