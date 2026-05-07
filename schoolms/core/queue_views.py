from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.permissions import can_manage_school
from core.models import AsyncJob


@login_required
def queue_monitor(request):
    """Operational queue monitor with safe degradation when broker/backend are unavailable."""
    user = request.user
    school = getattr(user, "school", None)
    if not school and not user.is_superuser:
        messages.error(request, "You are not attached to any school.")
        return redirect("accounts:dashboard")
    if not (user.is_superuser or can_manage_school(user)):
        messages.error(request, "You do not have permission to view queue monitoring.")
        return redirect("accounts:dashboard")

    jobs_qs = AsyncJob.objects.select_related("school", "created_by")
    if school and not user.is_superuser:
        jobs_qs = jobs_qs.filter(school=school)
    jobs = jobs_qs.order_by("-created_at")[:80]

    summary = {
        "pending": jobs_qs.filter(status="pending").count(),
        "running": jobs_qs.filter(status="running").count(),
        "success": jobs_qs.filter(status="success").count(),
        "failed": jobs_qs.filter(status="failed").count(),
    }

    broker_ok = True
    worker_ping = None
    inspect_error = ""
    try:
        from schoolms.celery_app import app as celery_app

        inspector = celery_app.control.inspect(timeout=1)
        worker_ping = inspector.ping() if inspector else None
        broker_ok = bool(worker_ping)
        if not broker_ok:
            inspect_error = "No Celery workers responded."
    except Exception as exc:
        broker_ok = False
        inspect_error = str(exc)[:240]

    result_backend_ok = True
    result_backend_error = ""
    result_rows = 0
    try:
        from django_celery_results.models import TaskResult

        q = TaskResult.objects.all()
        if school and not user.is_superuser:
            q = q.filter(task_kwargs__icontains=f'"school_id": {school.id}')
        result_rows = q.count()
    except Exception as exc:
        result_backend_ok = False
        result_backend_error = str(exc)[:240]

    context = {
        "school": school,
        "jobs": jobs,
        "summary": summary,
        "broker_ok": broker_ok,
        "worker_ping": worker_ping or {},
        "inspect_error": inspect_error,
        "result_backend_ok": result_backend_ok,
        "result_backend_error": result_backend_error,
        "result_rows": result_rows,
        "now": timezone.now(),
    }
    return render(request, "core/queue_monitor.html", context)
