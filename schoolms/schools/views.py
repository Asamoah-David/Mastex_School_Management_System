from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from accounts.models import User
from .models import School
import uuid
import logging

logger = logging.getLogger(__name__)


@login_required
def school_register(request):
    """School registration page - requires login."""
    if request.method == "POST":
        # School details
        school_name = request.POST.get("school_name", "").strip()
        school_email = request.POST.get("school_email", "").strip()
        school_phone = request.POST.get("school_phone", "").strip()
        school_address = request.POST.get("school_address", "").strip()
        
        # Admin user details
        admin_first_name = request.POST.get("admin_first_name", "").strip()
        admin_last_name = request.POST.get("admin_last_name", "").strip()
        admin_email = request.POST.get("admin_email", "").strip()
        admin_phone = request.POST.get("admin_phone", "").strip()
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")
        
        # Validation
        if not school_name:
            messages.error(request, "School name is required.")
            return render(request, "schools/register.html")
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "schools/register.html")
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "schools/register.html")
        
        if School.objects.filter(name=school_name).exists():
            messages.error(request, "A school with this name already exists.")
            return render(request, "schools/register.html")
        
        try:
            # Generate unique subdomain from school name
            # Only use alphanumeric characters and hyphens for subdomain
            safe_name = "".join(c for c in school_name.lower() if c.isalnum() or c == " ")
            subdomain = safe_name.replace(" ", "-") + "-" + str(uuid.uuid4())[:8]
            
            # Create school
            school = School.objects.create(
                name=school_name,
                subdomain=subdomain,
                email=school_email,
                phone=school_phone,
                address=school_address,
                is_active=True
            )
            
            # Create school admin user
            User.objects.create_user(
                username=username,
                email=admin_email,
                first_name=admin_first_name,
                last_name=admin_last_name,
                password=password,
                role="admin",
                school=school,
                phone=admin_phone
            )
            
            messages.success(request, f"School '{school_name}' registered successfully! Please login with your credentials.")
            return redirect("/accounts/login/")
            
        except IntegrityError as e:
            logger.error(f"Database integrity error during school registration: {e}")
            messages.error(request, "A school with similar details already exists. Please try a different name.")
            return render(request, "schools/register.html")
            
        except Exception as e:
            logger.error(f"Error during school registration: {e}")
            messages.error(request, f"An error occurred during registration. Please try again. Error: {str(e)}")
            return render(request, "schools/register.html")
    
    return render(request, "schools/register.html")
