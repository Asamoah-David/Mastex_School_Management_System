# Mastex SchoolOS

**Mastex SchoolOS** is a modern, **cloud-based school management system** (Django) from **Mastex Technologies**. It helps schools run **students, fees, academics, operations, and parent engagement** from one secure portal — designed for real school workflows, not generic CRM bolt-ons.

**Product site:** [mastexedu.online](https://mastexedu.online) · **Product owner:** Asamoah David · **Email:** mastex.digital.world@gmail.com · **WhatsApp:** [+233 544 789 716](https://wa.me/233544789716)

The platform suits **Software-as-a-Service (SaaS)** deployment: schools automate administration, collect fees with optional **Paystack** checkout, and keep families informed with in-app notifications and optional SMS.

---

## Features

### Student Management

* Student registration and profile management
* Parent contact information storage
* Organized academic record tracking

### User Authentication

* Secure login system
* Role-based access control for:

  * Administrators
  * Teachers
  * Students
  * Parents

### Fee Management

* Create and manage student fees
* Track payment history
* Monitor unpaid fees

### Online Payments

Integration with **Flutterwave** enables:

* Mobile Money payments
* Online card payments
* Automatic payment verification
* Retry failed transactions

### SMS Notifications

Integrated with **MNotify** to send SMS alerts such as:

* Payment confirmations
* Failed payment alerts
* Fee reminders
* Administrative notifications

### AI Assistant

The system integrates **OpenAI** to provide an AI assistant that helps users navigate the platform and answer questions.

### Administrative Dashboard

A central dashboard that allows administrators to:

* Manage students
* Monitor payments
* Send notifications
* Track system activity

---

## Technology Stack

Backend Framework

* **Django**

Database

* PostgreSQL

Payment Gateway

* **Flutterwave**

SMS Gateway

* **MNotify**

AI Integration

* **OpenAI**

Containerization

* **Docker**

Cloud Deployment

* **Render**

---

## Project Structure

```
school_saas/
│
├── accounts/
├── students/
├── payments/
├── fees/
├── core/
│
├── templates/
├── static/
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
└── README.md
```

---

## Installation

Clone the repository

```
git clone https://github.com/yourusername/school-saas.git
```

Navigate into the project

```
cd school-saas
```

Create a virtual environment

```
python -m venv venv
```

Activate the environment

Windows:

```
venv\Scripts\activate
```

Mac/Linux:

```
source venv/bin/activate
```

Install dependencies

```
pip install -r requirements.txt
```

Run migrations

```
python manage.py migrate
```

Start the server

```
python manage.py runserver
```

---

## Environment Variables

Create a `.env` file and add the following:

```
DJANGO_SECRET_KEY=
FLUTTERWAVE_PUBLIC_KEY=
FLUTTERWAVE_SECRET_KEY=
OPENAI_API_KEY=
MNOTIFY_API_KEY=
MNOTIFY_SENDER_ID=
ADMIN_PHONE=
```

---

## Documentation

- **Printable handbook (PDF-ready, school-facing, UI tour mockups + optional real screenshots):** open [docs/handbook/index.html](docs/handbook/index.html) in Chrome/Edge → Print → Save as PDF — see [docs/handbook/README.md](docs/handbook/README.md) (includes **`python manage.py capture_handbook_screenshots`** for Playwright captures) and [docs/handbook/images/README.md](docs/handbook/images/README.md)
- **School user manual (Markdown):** [docs/MASTEX_USER_GUIDE.md](docs/MASTEX_USER_GUIDE.md) (roles, scenarios, support vs Mastex provider)
- **Deployment:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) (environment variables, CI/CD, logging, Sentry, backups)

## Deployment

**Full guide:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) (environment variables, CI/CD, logging, Sentry, backups).  
**Env template:** copy [.env.example](.env.example) to `.env` (never commit secrets).

**CI:** GitHub Actions runs `check --deploy`, migration checks, `collectstatic`, and a Docker build (see `.github/workflows/ci.yml`).

**Docker / Render / Railway:** Migrations and `collectstatic` run on container start (`docker-entrypoint.sh`). Set `DATABASE_URL`, `SECRET_KEY`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`. Optional: `RUN_PREFLIGHT=1` to run `manage.py preflight` before Gunicorn.

If you use **Native Environment** (no Docker) on Render, set the **Start Command** to:
`python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn schoolms.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 2`

---

## Future Improvements

* Automated fee reminder scheduler
* Bulk SMS messaging
* Multi-school SaaS support
* Analytics dashboard
* Mobile app integration

---

## License

This project is open source and available under the MIT License.

---

## Mastex Technologies

**Mastex SchoolOS** is developed and product-managed by **Mastex Technologies**.

- **Website:** [https://mastexedu.online](https://mastexedu.online)  
- **Founder & Product Owner:** Asamoah David  
- **Email:** mastex.digital.world@gmail.com  
- **WhatsApp:** [+233 544 789 716](https://wa.me/233544789716)  

For school licensing, demos, implementation, or platform support, use the contacts above.
