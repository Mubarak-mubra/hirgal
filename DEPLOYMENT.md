# Deployment preparation

## Required services

- A PostgreSQL database. SQLite is supported for local development only; the
  invoice payment flow relies on database row locks to serialize payments.
- A deployment host that runs the WSGI application and can set environment
  variables. No provider-specific host or credentials are included here.
- Persistent storage for uploaded media, or a cloud media-storage service.

## Configure the environment

Use `.env.example` as the variable checklist. Set each value in the deployment
provider's environment settings. Django does not load a local `.env` file.
Generate a new `DJANGO_SECRET_KEY`, set explicit hostnames and HTTPS origins,
and use the database provider's PostgreSQL URL. Do not deploy the development
settings module.

The invoice "send" action currently opens WhatsApp with a prepared message; the
application does not send invoice email, so an SMTP provider is not required.

## Monthly rent drafts

Prepare monthly rent drafts from **Invoices → Prepare monthly rent invoices**.
The month defaults to the current month, and the user can change it before
confirming. The application creates one draft for each rental agreement that
covers the full month. Existing invoices for an agreement and month are skipped,
so repeating the action will not create duplicates. Drafts are not sent until
they are reviewed and sent individually. The invoice date is the day the drafts
are prepared, and the due date is seven calendar days later. No monthly scheduler
is needed for normal use.

The management command remains available for administrative backfills or
maintenance. Run it in the same environment and database as the web application:

```sh
DJANGO_SETTINGS_MODULE=config.production_settings python manage.py generate_monthly_rent_invoices --month 2026-10
```

Partial-month rent is not prorated automatically.

`TRUST_X_FORWARDED_PROTO=true` assumes the host's trusted proxy overwrites
`X-Forwarded-Proto`. Disable it if the deployment does not have that proxy
behavior. Keep HSTS at the short initial value until HTTPS is confirmed on the
production domain; increase it only after verifying the full host and subdomain
setup. Django will warn during `check --deploy` while HSTS is enabled but
subdomain and preload protection are off. Enable
`SECURE_HSTS_INCLUDE_SUBDOMAINS=true` and `SECURE_HSTS_PRELOAD=true` only after
confirming every affected subdomain is HTTPS-capable.

## Build and start

```sh
python -m pip install -r requirements.txt
DJANGO_SETTINGS_MODULE=config.production_settings python manage.py check --deploy
DJANGO_SETTINGS_MODULE=config.production_settings python manage.py migrate
DJANGO_SETTINGS_MODULE=config.production_settings python manage.py collectstatic --noinput
DJANGO_SETTINGS_MODULE=config.production_settings python manage.py createsuperuser
DJANGO_SETTINGS_MODULE=config.production_settings gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}
```

Keep the `MEDIA_ROOT` directory on a persistent volume or configure durable
object storage before accepting property photos and other uploads. Back up the
PostgreSQL database and test restoring a backup before launch.

## Before release

- Remove database dumps and logs from the repository and review whether prior
  Git history needs a sensitive-data cleanup.
- Set the environment values in the actual hosting provider and run
  `check --deploy` there.
- Confirm HTTPS redirects, static files, persistent media, migrations, backups,
  and restore behavior on a staging deployment. Verify WhatsApp invoice links
  with a real tenant phone number.
- Keep a rollback release and database backup available for the first deploy.
