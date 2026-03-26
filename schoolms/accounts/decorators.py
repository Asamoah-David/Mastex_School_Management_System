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
