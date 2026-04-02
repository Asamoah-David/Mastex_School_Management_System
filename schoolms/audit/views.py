from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from .models import AuditLog


@login_required
def audit_dashboard(request):
    """Audit log dashboard - superusers see all, school admins see their school's logs."""
    user = request.user
    
    # Check permissions - only superusers and school admins
    is_superuser = user.is_superuser or getattr(user, 'is_super_admin', False)
    is_school_admin = getattr(user, 'role', None) == 'admin' and hasattr(user, 'school')
    
    if not (is_superuser or is_school_admin):
        return redirect('home')
    
    # Base queryset
    if is_superuser:
        # Superusers see all logs
        logs = AuditLog.objects.all()
        can_view_all = True
    else:
        # School admins see only their school's logs
        school = getattr(user, 'school', None)
        if not school:
            return redirect('home')
        logs = AuditLog.objects.filter(school=school)
        can_view_all = False
    
    # Apply filters
    action_filter = request.GET.get('action', '')
    model_filter = request.GET.get('model', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '')
    
    if action_filter:
        logs = logs.filter(action=action_filter)
    
    if model_filter:
        logs = logs.filter(model_name__icontains=model_filter)
    
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)
    
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)
    
    if search_query:
        logs = logs.filter(
            Q(object_repr__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(model_name__icontains=search_query)
        )
    
    # Order by timestamp descending
    logs = logs.select_related('user', 'school').order_by('-timestamp')
    
    # Pagination
    paginator = Paginator(logs, 50)  # 50 items per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get unique action types and model names for filter dropdowns
    action_choices = [choice[0] for choice in AuditLog.ACTION_CHOICES]
    
    context = {
        'page_obj': page_obj,
        'action_choices': action_choices,
        'can_view_all': can_view_all,
        'filters': {
            'action': action_filter,
            'model': model_filter,
            'user': user_filter,
            'date_from': date_from,
            'date_to': date_to,
            'q': search_query,
        },
    }
    
    return render(request, 'audit/dashboard.html', context)


@login_required
def audit_log_detail(request, pk):
    """View details of a single audit log entry."""
    user = request.user
    
    is_superuser = user.is_superuser or getattr(user, 'is_super_admin', False)
    is_school_admin = getattr(user, 'role', None) == 'admin' and hasattr(user, 'school')
    
    if not (is_superuser or is_school_admin):
        return redirect('home')
    
    log_entry = AuditLog.objects.select_related('user', 'school').first()
    
    if not log_entry:
        # Try to find by pk
        try:
            log_entry = AuditLog.objects.get(pk=pk)
        except AuditLog.DoesNotExist:
            return redirect('audit:dashboard')
    
    # Check permissions for this specific log
    if not is_superuser:
        school = getattr(user, 'school', None)
        if school and log_entry.school and log_entry.school != school:
            return redirect('home')
    
    return render(request, 'audit/log_detail.html', {'log': log_entry})
