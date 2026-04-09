# Management School Management System

A modern **cloud-based School Management System** built with Django.
This platform helps schools manage **students, fees, payments, communication, and administrative tasks** from a centralized dashboard.

The system is designed as a **Software-as-a-Service (SaaS)** platform, enabling schools to automate operations, reduce manual work, and improve communication with parents.

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

## Author

Developed by **Asamoah David**
Computer Science Student | Full Stack Developer | Data Scientist
