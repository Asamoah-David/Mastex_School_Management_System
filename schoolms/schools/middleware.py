from django.shortcuts import redirect
from .models import School


class SchoolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip middleware for login/logout, registration, and static files
        exempt_paths = [
            '/accounts/login/',
            '/accounts/logout/',
            '/login/',
            '/logout/',
            '/register/',
            '/admin/login/',
            '/static/',
            '/media/',
        ]
        
        # Check if the path is exempt
        is_exempt = False
        for path in exempt_paths:
            if request.path.startswith(path):
                is_exempt = True
                break
        
        if is_exempt:
            return self.get_response(request)
        
        # Try to get school from subdomain
        host = request.get_host().split(':')[0]
        subdomain = host.split('.')[0]
        
        # Don't try to get school for base domain (like localhost or render)
        if subdomain and subdomain != 'localhost' and 'onrender' not in host:
            try:
                request.school = School.objects.get(subdomain=subdomain)
            except School.DoesNotExist:
                request.school = None
        else:
            request.school = None
        
        # Block non-superadmins from accessing Django admin
        if request.path.startswith('/admin/'):
            if not request.user.is_authenticated:
                return redirect('/accounts/login/')
            if not request.user.is_superuser and request.user.role != 'super_admin':
                return redirect('/accounts/school-dashboard/')
        
        return self.get_response(request)
