# Railway — before you push

## Migrations

Your `railway.json` **already runs** `python manage.py migrate --noinput` **before** Gunicorn on every deploy. No extra step required unless you use Docker instead of Nixpacks (then use the same command in the container entrypoint).

After adding apps like `token_blacklist`, ensure **one successful deploy** runs migrations (check deploy logs for `Applying ...`).

## Environment variables (set in Railway UI)

**Required**

- `SECRET_KEY`
- `DEBUG=False`
- `DATABASE_URL` (from Railway PostgreSQL or external e.g. Supabase)
- `ALLOWED_HOSTS` — include your Railway hostname, e.g. `yourapp.up.railway.app`
- `CSRF_TRUSTED_ORIGINS` — `https://yourapp.up.railway.app`

**Paystack / fees**

- `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`
- `PAYSTACK_WEBHOOK_SECRET` — **required** for webhooks to be accepted
- `PAYSTACK_PASS_FEE_TO_PAYER` — `True` (default) to uplift payer so net fee credit matches invoice
- `PAYSTACK_PROCESSING_FEE_PERCENT` — e.g. `1.95` (adjust to your Paystack tariff)

**Optional but recommended**

- `SENTRY_DSN`, `GIT_COMMIT_SHA`, `SENTRY_ENVIRONMENT`
- `CORS_ALLOWED_ORIGINS` if you have a separate front-end origin
- `REDIS_URL` if you add Redis for cache
- `EMAIL_*`, `SENDGRID_API_KEY` for mail
- `CRON_SECRET_KEY` if cron HTTP endpoints are used

## Fee routing (how it works in code)

- **School fee payments**: If `School.paystack_subaccount_code` is set, Paystack `subaccount` is sent → settlement goes to **that school subaccount**. If empty, payment goes to the **main Paystack account** (platform).
- **Subscriptions** (`pay_subscription`): Initializes **without** `subaccount` → **platform** Paystack account.

## After push

1. Open deploy logs → confirm `migrate` OK.  
2. Hit `https://<host>/health/`.  
3. Test one fee payment and one subscription in staging.
