from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError

from accounts.models import User
from .models import School
import uuid
import logging

logger = logging.getLogger(__name__)


@login_required
def school_list(request):
    """
    Platform view: list all schools (superusers / super_admin only).
    """
    if not (request.user.is_superuser or getattr(request.user, "is_super_admin", False)):
        return redirect("accounts:dashboard")
    schools = School.objects.all().order_by("-is_active", "name")
    return render(request, "schools/school_list.html", {"schools": schools})


@login_required
def school_features(request, pk):
    """
    Platform-only: enable/disable features per school.
    """
    if not (request.user.is_superuser or getattr(request.user, "is_super_admin", False)):
        return redirect("accounts:dashboard")

    from .features import ensure_features_exist
    from .models import SchoolFeature

    school = School.objects.filter(pk=pk).first()
    if not school:
        return redirect("schools:school_list")

    ensure_features_exist(school)
    features = list(SchoolFeature.objects.filter(school=school).order_by("key"))

    if request.method == "POST":
        enabled_keys = set(request.POST.getlist("enabled"))
        for f in features:
            f.enabled = f.key in enabled_keys
        SchoolFeature.objects.bulk_update(features, ["enabled"])
        messages.success(request, "School features updated.")
        return redirect("schools:school_features", pk=school.pk)

    return render(request, "schools/school_features.html", {"school": school, "features": features})


@login_required
def school_register(request):
    """
    School registration page.

    Only platform superusers / super_admins are allowed to create new schools
    and their initial admin accounts. Regular users and school admins cannot
    self-register schools.
    """
    # Enforce that only platform-level admins can register schools
    if not (request.user.is_superuser or getattr(request.user, "is_super_admin", False)):
        messages.error(request, "Only the platform administrator can register new schools.")
        return redirect("/accounts/dashboard/")
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


@login_required
def school_settings(request):
    """Update school profile (logo URL, academic year, Paystack settings). School admin only."""
    from accounts.permissions import is_school_admin
    if not (request.user.is_superuser or is_school_admin(request.user)):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "Select a school first.")
        return redirect("accounts:dashboard")
    if request.method == "POST":
        school.logo_url = request.POST.get("logo_url", "").strip() or ""
        school.academic_year = request.POST.get("academic_year", "").strip() or ""
        school.name = request.POST.get("name", "").strip() or school.name
        school.email = request.POST.get("email", "").strip() or school.email
        school.phone = request.POST.get("phone", "").strip() or school.phone
        school.address = request.POST.get("address", "").strip() or school.address
        
        # Paystack settings for receiving payments directly to school's account
        school.paystack_subaccount_code = request.POST.get("paystack_subaccount_code", "").strip() or ""
        school.paystack_bank_name = request.POST.get("paystack_bank_name", "").strip() or ""
        school.paystack_account_number = request.POST.get("paystack_account_number", "").strip() or ""
        school.paystack_account_name = request.POST.get("paystack_account_name", "").strip() or ""
        
        school.save()
        messages.success(request, "School settings saved.")
        return redirect("schools:school_settings")
    return render(request, "schools/school_settings.html", {"school": school})


