from django.shortcuts import redirect
from .models import School


class SchoolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0]
        subdomain = host.split('.')[0]
        try:
            request.school = School.objects.get(subdomain=subdomain)
        except School.DoesNotExist:
            request.school = None
        
        # Block non-superadmins from accessing Django admin
        if request.path.startswith('/admin/'):
            if not request.user.is_authenticated:
                return redirect('accounts:login')
            if not request.user.is_superuser and request.user.role != 'super_admin':
                return redirect('accounts:school_dashboard')
        
        return self.get_response(request)
