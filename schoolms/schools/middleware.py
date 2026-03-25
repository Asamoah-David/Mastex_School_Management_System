from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from .models import School


class SchoolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip all middleware processing for these paths (no redirects on login/dashboard)
        skip_paths = [
            "/", "/accounts/login/", "/accounts/logout/", "/accounts/dashboard/", "/accounts/school-dashboard/",
            "/login/", "/logout/", "/register/", "/admin/login/", "/portal/",
        ]
        # Allow subscription and payment related paths for expired schools
        subscription_paths = [
            "/finance/subscription/", "/finance/pay-subscription/", "/finance/subscription-callback/",
            "/finance/subscription-expired/", "/accounts/login/", "/accounts/logout/",
        ]
        
        if request.path in skip_paths:
            return self.get_response(request)
        if any(request.path.startswith(p) for p in ["/static/", "/media/", "/admin/jsi18n/", "/portal"]):
            return self.get_response(request)
        
        # Try to get school from subdomain only for non-base domains
        host = request.get_host().split(":")[0]
        
        # Only try subdomain lookup for actual subdomains (not localhost or render)
        if "." in host and "localhost" not in host and "onrender" not in host:
            subdomain = host.split(".")[0]
            try:
                request.school = School.objects.get(subdomain=subdomain)
            except School.DoesNotExist:
                request.school = None
        else:
            request.school = None
        
        # Block non-superadmins from accessing Django admin
        if request.path.startswith("/admin/"):
            if not request.user.is_authenticated:
                return redirect(reverse("accounts:login"))
            if not request.user.is_superuser and request.user.role != "super_admin":
                return redirect(reverse("accounts:school_dashboard"))
        
        # Check if user's school is active (allow superusers/super_admins to always access)
        if request.user.is_authenticated:
            user_school = getattr(request.user, 'school', None)
            if user_school and not getattr(request.user, 'is_superuser', False) and getattr(request.user, 'role', None) != 'super_admin':
                if not user_school.is_active:
                    # Logout and redirect to login with message
                    from django.contrib.auth import logout
                    logout(request)
                    return redirect(f"{reverse('accounts:login')}?inactive=1")
                
                # Check subscription status
                if user_school.subscription_status == 'expired':
                    # Allow access to subscription-related pages only
                    allowed = any(request.path.startswith(p) for p in subscription_paths)
                    if not allowed:
                        return render(request, 'finance/subscription_expired.html', {'school': user_school})
                
                # Check if subscription has expired based on end date (even if status is 'active')
                elif user_school.subscription_status == 'active' and user_school.subscription_end_date:
                    if user_school.subscription_end_date < timezone.now():
                        # Update status to expired
                        user_school.subscription_status = 'expired'
                        user_school.save(update_fields=['subscription_status'])
                        allowed = any(request.path.startswith(p) for p in subscription_paths)
                        if not allowed:
                            return render(request, 'finance/subscription_expired.html', {'school': user_school})
        
        return self.get_response(request)
