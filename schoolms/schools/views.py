from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import User
from .models import School
from core.pagination import paginate
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

    if request.method == "POST":
        action = request.POST.get("bulk_action", "")
        selected_ids = request.POST.getlist("selected_schools")
        if selected_ids and action:
            qs = School.objects.filter(id__in=selected_ids)
            if action == "activate":
                count = qs.update(is_active=True)
                messages.success(request, f"Activated {count} school(s).")
            elif action == "deactivate":
                count = qs.update(is_active=False)
                messages.success(request, f"Deactivated {count} school(s).")
        return redirect("schools:school_list")

    schools = School.objects.all().order_by("-is_active", "name")

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if q:
        schools = schools.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
    if status:
        schools = schools.filter(subscription_status=status)

    page_obj = paginate(request, schools, per_page=25)
    return render(request, "schools/school_list.html", {"schools": page_obj, "page_obj": page_obj, "q": q, "status": status})


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

        if not username:
            messages.error(request, "Admin username is required.")
            return render(request, "schools/register.html")

        if not password:
            messages.error(request, "Password is required.")
            return render(request, "schools/register.html")
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "schools/register.html")

        try:
            validate_password(
                password,
                user=User(
                    username=username,
                    email=admin_email,
                    first_name=admin_first_name,
                    last_name=admin_last_name,
                ),
            )
        except ValidationError as e:
            for msg in e.messages:
                messages.error(request, msg)
            return render(request, "schools/register.html")
        
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return render(request, "schools/register.html")
        
        if School.objects.filter(name=school_name).exists():
            messages.error(request, "A school with this name already exists.")
            return render(request, "schools/register.html")
        
        try:
            with transaction.atomic():
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
                    role="school_admin",
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
            messages.error(request, "An error occurred during registration. Please try again.")
            return render(request, "schools/register.html")

    return render(request, "schools/register.html")


@login_required
def school_settings(request):
    """Update school profile (logo URL, academic year, Paystack payout setup). School leadership only."""
    from accounts.permissions import is_school_leadership
    from django.conf import settings as django_settings
    from django.utils import timezone as tz

    if not (request.user.is_superuser or is_school_leadership(request.user)):
        return redirect("accounts:school_dashboard")
    school = getattr(request.user, "school", None)
    if not school and not request.user.is_superuser:
        return redirect("accounts:dashboard")
    if not school:
        messages.error(request, "Select a school first.")
        return redirect("accounts:dashboard")

    if request.method == "POST":
        section = request.POST.get("section", "basic").strip()

        if section == "basic":
            school.logo_url = request.POST.get("logo_url", "").strip() or ""
            school.academic_year = request.POST.get("academic_year", "").strip() or ""
            school.name = request.POST.get("name", "").strip() or school.name
            school.email = request.POST.get("email", "").strip() or school.email
            school.phone = request.POST.get("phone", "").strip() or school.phone
            school.address = request.POST.get("address", "").strip() or school.address
            school.save()
            messages.success(request, "School settings saved.")
            return redirect("schools:school_settings")

        if section == "payout":
            bank_code = request.POST.get("paystack_bank_code", "").strip()
            account_number = request.POST.get("paystack_account_number", "").strip()
            account_name = request.POST.get("paystack_account_name", "").strip()
            bank_name = request.POST.get("paystack_bank_name", "").strip()

            if not bank_code or not account_number or not account_name:
                messages.error(request, "Bank code, account number, and account name are all required.")
                return redirect("schools:school_settings")

            if not bool(getattr(django_settings, "PAYSTACK_SECRET_KEY", "")):
                messages.error(request, "Paystack is not configured on the platform (missing PAYSTACK_SECRET_KEY).")
                return redirect("schools:school_settings")

            from finance.paystack_service import paystack_service

            school.paystack_bank_code = bank_code
            school.paystack_bank_name = bank_name
            school.paystack_account_number = account_number
            school.paystack_account_name = account_name
            school.paystack_subaccount_status = "pending"
            school.paystack_subaccount_last_error = ""
            school.save(update_fields=[
                "paystack_bank_code", "paystack_bank_name",
                "paystack_account_number", "paystack_account_name",
                "paystack_subaccount_status", "paystack_subaccount_last_error",
            ])

            logger.info(
                "school_payout_setup: school=%s bank_code=%s account=***%s by user=%s",
                school.pk, bank_code, account_number[-4:] if len(account_number) >= 4 else "???",
                request.user.pk,
            )

            resp = paystack_service.create_subaccount(
                business_name=school.name,
                settlement_bank=bank_code,
                account_number=account_number,
                percentage_charge=getattr(django_settings, "PAYSTACK_PLATFORM_FEE_PERCENT", 0),
                primary_contact_email=school.email or None,
                primary_contact_name=account_name or None,
                primary_contact_phone=school.phone or None,
                metadata={"school_id": school.pk},
            )

            if resp.get("status") and resp.get("data", {}).get("subaccount_code"):
                code = resp["data"]["subaccount_code"]
                school.paystack_subaccount_code = code
                school.paystack_subaccount_status = "active"
                school.paystack_subaccount_last_error = ""
                school.paystack_subaccount_last_synced_at = tz.now()
                school.save(update_fields=[
                    "paystack_subaccount_code", "paystack_subaccount_status",
                    "paystack_subaccount_last_error", "paystack_subaccount_last_synced_at",
                ])
                logger.info("school_payout_setup: OK school=%s subaccount=%s", school.pk, code)
                messages.success(request, f"Payout setup complete — subaccount {code} is active. Parents can now pay fees online.")
            else:
                err = resp.get("message") or "Unknown error from Paystack."
                school.paystack_subaccount_status = "failed"
                school.paystack_subaccount_last_error = str(err)[:2000]
                school.paystack_subaccount_last_synced_at = tz.now()
                school.save(update_fields=[
                    "paystack_subaccount_status", "paystack_subaccount_last_error",
                    "paystack_subaccount_last_synced_at",
                ])
                logger.warning("school_payout_setup: FAILED school=%s error=%s", school.pk, err)
                messages.error(request, f"Paystack subaccount creation failed: {err}")

            return redirect("schools:school_settings")

    return render(request, "schools/school_settings.html", {
        "school": school,
        "paystack_configured": bool(getattr(django_settings, "PAYSTACK_SECRET_KEY", "")),
    })


