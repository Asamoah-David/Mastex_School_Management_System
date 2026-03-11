from django.shortcuts import redirect
from django.urls import reverse # Added import for reverse
from .models import School


class SchoolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip all middleware processing for these paths
        if request.path in ["/accounts/login/", "/accounts/logout/", "/login/", "/logout/", "/register/", "/admin/login/", "/portal/"]:
            return self.get_response(request)
        
        # Skip for paths starting with these
        if any(request.path.startswith(path) for path in ["/static/", "/media/", "/admin/jsi18n/", "/portal"]):
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
                return redirect(reverse("accounts:login")) # Using reverse()
            if not request.user.is_superuser and request.user.role != "super_admin":
                return redirect(reverse("accounts:school_dashboard")) # Using reverse()
        
        return self.get_response(request)