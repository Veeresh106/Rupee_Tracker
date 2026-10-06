# ExpenseTracker

A Django Personal Expense Tracker built for the SVCET Hackathon – Powered by LEARNSQUARE.

## Features
- User registration, login, and logout
- Category creation and management
- Monthly budget setup per category
- Expense tracking with validation
- Budget alerts at 80% and 100% usage
- Dashboard summary and spending reports
- SQLite database backend

## Run locally

Requires Python 3.13 or newer. Create and activate a virtual environment, then:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/

## Test
```bash
python manage.py check
python manage.py test
```

Create an administrator with `python manage.py createsuperuser` to use `/admin/`.

## Deployment configuration

Set `DJANGO_SECRET_KEY` to a private random value, `DJANGO_DEBUG=false`, and
`DJANGO_ALLOWED_HOSTS` to a comma-separated list of the deployment hostnames.
Run `python manage.py collectstatic` before deploying. The default SQLite
database is intended for local and small demonstration use; use a managed
database for a multi-user production deployment.
