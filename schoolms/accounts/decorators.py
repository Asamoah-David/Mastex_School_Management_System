"""
Custom decorators for role-based access control.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_required(view_func):
    """Decorator that requires user to be a school admin."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if request.user.role == 'school_admin' or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def role_required(*allowed_roles):
    """
    Decorator that requires user to have one of the specified roles.
    Usage: @role_required('school_admin', 'teacher')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            user_role = getattr(request.user, 'role', None)
            
            if user_role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('home')
        
        return wrapper
    return decorator


def teacher_required(view_func):
    """Decorator that requires user to be a teacher."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if request.user.role in ['school_admin', 'teacher'] or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def school_required(view_func):
    """Decorator that requires user to be associated with a school."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if hasattr(request.user, 'school') and request.user.school:
            return view_func(request, *args, **kwargs)
        
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'Your account is not associated with a school.')
        return redirect('home')
    
    return wrapper


def finance_required(view_func):
    """Decorator that requires user to have finance permissions."""
    from .permissions import can_manage_finance
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_manage_finance(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def library_required(view_func):
    """Decorator that requires user to have library permissions."""
    from .permissions import can_manage_library
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_manage_library(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def health_required(view_func):
    """Decorator that requires user to have health/medical permissions."""
    from .permissions import can_manage_health
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_manage_health(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def admissions_required(view_func):
    """Decorator that requires user to have admissions permissions."""
    from .permissions import can_manage_admissions
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_manage_admissions(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def hostel_required(view_func):
    """Decorator that requires user to have hostel permissions."""
    from .permissions import can_manage_hostel
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_manage_hostel(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def academic_required(view_func):
    """Decorator that requires user to have academic content creation permissions."""
    from .permissions import can_create_academic_content
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_create_academic_content(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('home')
    
    return wrapper


def results_upload_required(view_func):
    """Decorator that requires user to have result upload permissions."""
    from .permissions import can_upload_results
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        if can_upload_results(request.user):
            return view_func(request, *args, **kwargs)
        
        messages.error(request, 'You do not have permission to upload results.')
        return redirect('home')
    
    return wrapper
